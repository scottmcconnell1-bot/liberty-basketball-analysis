"""Make/miss clip model - step 2: train / evaluate a 3-class video model (0 not a shot, 1 miss, 2 make).

Backbone: torchvision r2plus1d_18 (Kinetics-400 pretrained), fine-tuned end to end.
Input: hoop clips from extract_clips.py (clips7 N=32, or 52d N=44).

Spec 52 / 52d defaults (R4/R5): bf16 autocast without GradScaler; WeightedRandomSampler class-balanced
(w = 1/max(cnt,1)); plain CE + label_smoothing 0.05 (no class weights); softer aug; lr 2e-4, bs 8,
AdamW wd 0.05, OneCycle pct_start 0.15. Spec 52d head = R4 Sequential(Dropout(0.5), Linear(512,3)),
single input (no seq); time-shift +-1 frame; predict bs forced to 8. choose_e picks E via nested LOGO
split; logo/fit use fixed E. Speed guard (52d G8): measured train s/step > 2x probe 0.53 -> STOP.

Usage:
  python train_clip.py choose_e <clips_dir> <out_dir> --films adrian notus gvg hsb rimrock
  python train_clip.py logo     <clips_dir> <out_dir> --films ... --epochs E --seeds 0 1 2
  python train_clip.py fit      <clips_dir> <out_dir> --films ... --epochs E --seeds 0 1 2 3 4 [--save-dir d]
  python train_clip.py cross    <clips_dir> <out_dir> --train ... --test ...
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

# Torch is required for train/predict; optional so GPU-free unit tests can import
# seq_follower on hosts without torch (WSL system python).
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import WeightedRandomSampler
    HAS_TORCH = True
except ImportError:  # pragma: no cover
    torch = None
    nn = None
    F = None
    WeightedRandomSampler = None
    HAS_TORCH = False

try:
    import torchvision
except ImportError:  # pragma: no cover
    torchvision = None

if HAS_TORCH:
    MEAN = torch.tensor([0.43216, 0.394666, 0.37645]).view(1, 3, 1, 1, 1)
    STD = torch.tensor([0.22803, 0.22145, 0.216989]).view(1, 3, 1, 1, 1)
else:  # pragma: no cover
    MEAN = None
    STD = None

# R5 fixed wrap order for nested LOGO split
FILM_ORDER = ["adrian", "notus", "gvg", "hsb", "rimrock"]

# Spec 52c helper (kept pure; 52d model does not consume seq)
SEQ_WINDOW_MS = 6000

# Spec 52d pins
PREDICT_BS = 8  # force; train_clip.predict default was 16
TIME_SHIFT_FRAMES = 1  # +-1 frame at STEP=0.16 (= +-0.16 s; same physical jitter as R4 +-2 @ 0.08)
SPEED_PROBE_S_PER_STEP = 0.53  # review52/gpu_probe52d.txt T=44 bs8
SPEED_GUARD_MAX_S_PER_STEP = 2.0 * SPEED_PROBE_S_PER_STEP  # 1.06; G8 STOP for Scott


def load(clips_dir, films):
    X, Y, T, Fm = [], [], [], []
    for f in films:
        d = np.load(Path(clips_dir) / f"{f}.npz")
        X.append(d["clips"]); Y.append(d["y"].astype(np.int64)); T.append(d["t_ms"]); Fm += [f] * len(d["y"])
    return np.concatenate(X), np.concatenate(Y), np.concatenate(T), np.array(Fm)


def seq_follower(T, window_ms=SEQ_WINDOW_MS):
    """Per-film sequence flag: 1.0 iff another candidate t_ms in (t, t+window_ms].

    Computed over one film's full candidate T (incl. -1/0 rows). Never concat across
    films. Returns float32 (N, 1) with values in {0.0, 1.0}. Inclusive end.
    """
    T = np.asarray(T, dtype=np.int64).reshape(-1)
    n = len(T)
    out = np.zeros((n, 1), np.float32)
    if n == 0:
        return out
    order = np.argsort(T, kind="mergesort")
    Ts = T[order]
    for rank in range(n):
        t = int(Ts[rank])
        # first index with value > t; first with value > t+window
        lo = int(np.searchsorted(Ts, t, side="right"))
        hi = int(np.searchsorted(Ts, t + int(window_ms), side="right"))
        if lo < hi:
            out[order[rank], 0] = 1.0
    return out


def seq_follower_per_film(T, Fm):
    """Compute seq_follower independently per film; cross-film concat is forbidden."""
    T = np.asarray(T)
    Fm = np.asarray(Fm)
    out = np.zeros((len(T), 1), np.float32)
    for f in np.unique(Fm):
        m = Fm == f
        out[m] = seq_follower(T[m])
    return out


if HAS_TORCH:
    class ClipModel(nn.Module):
        """Spec 52d / R4: r2plus1d_18; fc = Sequential(Dropout(0.5), Linear(512, 3)); no seq."""

        def __init__(self, backbone):
            super().__init__()
            self.backbone = backbone
            # R4 / ens51 / final51 checkpoint keys: fc.0 (Dropout), fc.1 (Linear)
            self.backbone.fc = nn.Sequential(
                nn.Dropout(0.5),
                nn.Linear(512, 3),
            )

        def forward(self, x):
            # x: (B,3,T,H,W) -> logits (B,3). Single input; no seq, no concat.
            return self.backbone(x)

    # Alias kept so older 52c tests/imports that mention SeqClipModel fail loudly if misused.
    SeqClipModel = None  # type: ignore
else:  # pragma: no cover
    ClipModel = None  # type: ignore
    SeqClipModel = None  # type: ignore


def to_tensor(xb):  # uint8 (B,T,H,W,3) BGR -> float (B,3,T,H,W) RGB normalised
    x = torch.from_numpy(xb).to("cuda", non_blocking=True).float().div_(255.0)
    x = x[..., [2, 1, 0]].permute(0, 4, 1, 2, 3)
    return (x - MEAN.cuda()) / STD.cuda()


def augment(x, soft=True, time_shift_frames=TIME_SHIFT_FRAMES):
    """x: (B,3,T,H,W) normalised. GPU-side augmentation per sample.
    soft=True (R4 default): bright/contr 0.7-1.3, sat 0.6-1.4, gray 10%, blur 20%, flip 20%.
    soft=False: previous stronger ranges (explicit --strong-aug).
    time_shift_frames: 52d pin +-1 (default); was +-2 under clips7 STEP=0.08."""
    B, C, T, H, W = x.shape
    out = torch.empty_like(x)
    br_lo, br_hi = (0.7, 1.3) if soft else (0.6, 1.4)
    sa_lo, sa_hi = (0.6, 1.4) if soft else (0.5, 1.5)
    gray_p = 0.10 if soft else 0.15
    blur_p = 0.20 if soft else 0.30
    flip_p = 0.20 if soft else 0.50
    ts = int(time_shift_frames)
    for b in range(B):
        v = x[b]
        # time shift +-ts frames (edge pad); 52d pin ts=1
        s = int(torch.randint(-ts, ts + 1, (1,))) if ts > 0 else 0
        if s:
            v = torch.roll(v, s, dims=1)
            if s > 0: v[:, :s] = v[:, s:s + 1]
            else: v[:, s:] = v[:, s - 1:s]
        # random resized crop (scale 0.75-1.0 of area, aspect jitter), shift = hoop box error
        sc = float(torch.empty(1).uniform_(0.80, 1.0))
        ch, cw = int(H * sc), int(W * sc * float(torch.empty(1).uniform_(0.9, 1.1)))
        cw = min(cw, W)
        y0 = int(torch.randint(0, H - ch + 1, (1,))); x0 = int(torch.randint(0, W - cw + 1, (1,)))
        v = v[:, :, y0:y0 + ch, x0:x0 + cw]
        v = F.interpolate(v, size=(H, W), mode="bilinear", align_corners=False)
        # photometric (in de-normalised space)
        v = v * STD.cuda()[0] + MEAN.cuda()[0]
        br = float(torch.empty(1).uniform_(br_lo, br_hi)); co = float(torch.empty(1).uniform_(br_lo, br_hi))
        sa = float(torch.empty(1).uniform_(sa_lo, sa_hi))
        m = v.mean()
        v = (v - m) * co + m
        v = v * br
        g = v.mean(0, keepdim=True)
        v = g + (v - g) * sa
        if torch.rand(1) < gray_p:
            v = g.expand_as(v).clone()
        v = v + torch.empty(3, 1, 1, 1, device=v.device).uniform_(-0.06, 0.06)  # colour cast
        if torch.rand(1) < blur_p:
            k = torch.tensor([1., 2., 1.], device=v.device); k = (k[:, None] * k[None, :]) / 16
            v = F.conv2d(v.reshape(-1, 1, H, W), k.view(1, 1, 3, 3), padding=1).reshape(3, T, H, W)
        if torch.rand(1) < flip_p:
            v = torch.flip(v, dims=[3])
        v = v.clamp(0, 1)
        out[b] = (v - MEAN.cuda()[0]) / STD.cuda()[0]
    return out


def make_model(device="cuda"):
    if not HAS_TORCH or torchvision is None:
        raise RuntimeError("make_model requires torch and torchvision")
    backbone = torchvision.models.video.r2plus1d_18(
        weights=torchvision.models.video.R2Plus1D_18_Weights.KINETICS400_V1
    )
    return ClipModel(backbone).to(device)


def _sample_indices(Y, n, use_sampler=True):
    """Class-balanced WeightedRandomSampler (R4): w = 1/max(cnt,1) per class. Or plain permutation."""
    if not use_sampler:
        return np.random.permutation(n)
    cnt = np.bincount(Y, minlength=3).astype(np.float64)
    w_class = 1.0 / np.maximum(cnt, 1.0)
    weights = torch.as_tensor(w_class[Y], dtype=torch.double)
    sampler = WeightedRandomSampler(weights, num_samples=n, replacement=True)
    return np.array(list(sampler), dtype=np.int64)


def _speed_guard_stop(s_per_step, spill=False):
    """Spec 52d G8: abort with a clear STOP for Scott; no silent bs change."""
    if spill:
        msg = (
            "STOP for Scott: shared-memory spill seen during 52d train "
            f"(probe {SPEED_PROBE_S_PER_STEP:.3f} s/step for T=44 bs8). "
            "No silent batch-size change (bs stays 8 PINNED)."
        )
    else:
        msg = (
            "STOP for Scott: measured train "
            f"{s_per_step:.3f} s/step > 2x probe {SPEED_PROBE_S_PER_STEP:.3f} s/step "
            f"(limit {SPEED_GUARD_MAX_S_PER_STEP:.3f} s/step) for 52d T=44 bs8 setup. "
            "No silent batch-size change (bs stays 8 PINNED)."
        )
    print(msg, flush=True)
    raise SystemExit(msg)


def train(X, Y, epochs=18, bs=8, lr=2e-4, seed=0, soft_aug=True, use_sampler=True,
          class_weights=False, use_scaler=False, eval_each_epoch=None, seq=None,
          time_shift_frames=TIME_SHIFT_FRAMES, speed_guard=True):
    """Train; if eval_each_epoch(model, ep) is set, call it after each epoch (1-indexed).

    Spec 52d: seq is accepted but ignored (R4 head has no seq input). time_shift_frames=1.
    speed_guard: after the first epoch, if mean s/step > 2x probe 0.53 -> STOP for Scott.
    """
    del seq  # 52d: no seq; accept kw for call-site compatibility
    torch.manual_seed(seed); np.random.seed(seed)
    keep = Y >= 0
    X, Y = X[keep], Y[keep]
    model = make_model()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.05)
    steps = max(1, epochs * int(np.ceil(len(Y) / bs)))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.15)
    scaler = torch.amp.GradScaler() if use_scaler else None
    w = None
    if class_weights:
        cnt = np.bincount(Y, minlength=3).astype(np.float32)
        w = torch.tensor(cnt.sum() / (3 * np.maximum(cnt, 1)), device="cuda")
    step_times = []
    guard_checked = False
    for ep in range(epochs):
        model.train()
        idx = _sample_indices(Y, len(Y), use_sampler=use_sampler)
        tot, n = 0.0, 0
        for i in range(0, len(idx), bs):
            t_step0 = time.perf_counter()
            b = idx[i:i + bs]
            xb = augment(to_tensor(X[b]), soft=soft_aug, time_shift_frames=time_shift_frames)
            yb = torch.from_numpy(Y[b]).cuda()
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(xb)
                if w is not None:
                    loss = F.cross_entropy(logits, yb, weight=w, label_smoothing=0.05)
                else:
                    loss = F.cross_entropy(logits, yb, label_smoothing=0.05)
            opt.zero_grad(set_to_none=True)
            if scaler is not None:
                scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
            else:
                loss.backward(); opt.step()
            sched.step()
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            step_times.append(time.perf_counter() - t_step0)
            tot += float(loss) * len(b); n += len(b)
        mean_s = float(np.mean(step_times)) if step_times else 0.0
        print(
            f"    epoch {ep + 1}/{epochs} loss {tot / max(n, 1):.3f} "
            f"s/step {mean_s:.3f}",
            flush=True,
        )
        if speed_guard and not guard_checked and step_times:
            guard_checked = True
            # Spill heuristic: step time already huge vs probe (same G8 STOP path).
            if mean_s > SPEED_GUARD_MAX_S_PER_STEP:
                spill = mean_s > (10.0 * SPEED_PROBE_S_PER_STEP)
                _speed_guard_stop(mean_s, spill=spill)
        if eval_each_epoch is not None:
            eval_each_epoch(model, ep + 1)
    return model


def predict(model, X, bs=None, tta=True, seq=None):
    """Predict softmax. Spec 52d: FORCE bs=8; seq accepted but ignored (no seq head)."""
    if not HAS_TORCH:
        raise RuntimeError("predict requires torch")
    del seq  # 52d: no seq
    if bs is None:
        bs = PREDICT_BS
    with torch.no_grad():
        model.eval()
        P = []
        for i in range(0, len(X), bs):
            xb = to_tensor(X[i:i + bs])
            with torch.autocast("cuda", dtype=torch.bfloat16):
                p = F.softmax(model(xb).float(), 1)
                if tta:
                    p = (p + F.softmax(model(torch.flip(xb, dims=[4])).float(), 1)) / 2
            P.append(p.cpu().numpy())
        return np.concatenate(P)


def miss_recall(Y, P):
    """R5/C3: mean(pred_class > 0 | Y == 1)."""
    pred = P.argmax(1)
    m = Y == 1
    if not m.any():
        return 0.0
    return float((pred[m] > 0).mean())


def shots_correct_overall(Y, P):
    pred = P.argmax(1)
    shots = Y > 0
    if not shots.any():
        return 0.0
    return float((pred[shots] == Y[shots]).mean())


def report(name, Y, P):
    pred = P.argmax(1)
    keep = Y >= 0
    Y, pred, P = Y[keep], pred[keep], P[keep]
    shots = Y > 0
    mm = shots & (pred > 0)
    r = {
        "n": int(len(Y)), "real_shots": int(shots.sum()), "makes": int((Y == 2).sum()),
        "3class_acc": float((pred == Y).mean()) if len(Y) else None,
        "shots_kept_as_shot": float((pred[shots] > 0).mean()) if shots.any() else None,
        "makemiss_acc_on_kept_shots": float((pred[mm] == Y[mm]).mean()) if mm.any() else None,
        "shots_correct_overall": float((pred[shots] == Y[shots]).mean()) if shots.any() else None,
        "miss_recall": miss_recall(Y, P),
        "make_recall": float((pred[Y == 2] == 2).mean()) if (Y == 2).any() else None,
        "make_precision": float((Y[pred == 2] == 2).mean()) if (pred == 2).any() else None,
        "nonshot_rejected": float((pred[Y == 0] == 0).mean()) if (Y == 0).any() else None,
        "confusion_rows_true_0_1_2": [[int(((Y == a) & (pred == b)).sum()) for b in range(3)] for a in range(3)],
    }
    print(f"  == {name}: " + json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
    return r


def inner_val_game(held_out, remaining):
    """R5: next game in FILM_ORDER after held_out, wrapping, skipping held_out, must be in remaining."""
    if held_out in FILM_ORDER:
        i0 = FILM_ORDER.index(held_out)
        order = FILM_ORDER
    else:
        order = list(remaining)
        i0 = -1
    for k in range(1, len(order) + 1):
        cand = order[(i0 + k) % len(order)]
        if cand != held_out and cand in remaining:
            return cand
    return remaining[0]


def choose_e(clips_dir, films, out_dir, max_epochs=18, seed=0, soft_aug=True):
    """R5 nested split: per outer fold, inner-val = wrap-next; best epoch by miss_recall (tie sco); E=median."""
    X, Y, T, Fm = load(clips_dir, films)
    del T  # 52d: no seq from T
    fold_best = {}
    for held in films:
        remaining = [f for f in films if f != held]
        ival = inner_val_game(held, remaining)
        itrain = [f for f in remaining if f != ival]
        print(f"-- choose_e hold {held}: inner-train {itrain} inner-val {ival}", flush=True)
        tr = np.isin(Fm, itrain)
        va = Fm == ival
        Xtr, Ytr = X[tr], Y[tr]
        Xva, Yva = X[va], Y[va]
        state = {"best_ep": 1, "best_mr": -1.0, "best_sco": -1.0}

        def on_epoch(model, ep):
            P = predict(model, Xva, bs=PREDICT_BS, seq=None)
            mr = miss_recall(Yva, P)
            sco = shots_correct_overall(Yva, P)
            print(f"      val ep {ep}: miss_recall={mr:.4f} sco={sco:.4f}", flush=True)
            if mr > state["best_mr"] or (mr == state["best_mr"] and sco > state["best_sco"]):
                state["best_ep"], state["best_mr"], state["best_sco"] = ep, mr, sco

        train(Xtr, Ytr, epochs=max_epochs, seed=seed, soft_aug=soft_aug, eval_each_epoch=on_epoch,
              seq=None)
        fold_best[held] = {
            "inner_val": ival, "inner_train": itrain,
            "best_epoch": int(state["best_ep"]),
            "miss_recall": state["best_mr"], "shots_correct_overall": state["best_sco"],
        }
        print(f"  fold {held}: best_epoch={state['best_ep']}", flush=True)
        torch.cuda.empty_cache()
    epochs = [fold_best[f]["best_epoch"] for f in films]
    E = int(np.median(epochs))
    result = {"folds": fold_best, "best_epochs": epochs, "E": E, "seed": seed, "max_epochs": max_epochs}
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(out / "choose_e.json", "w"), indent=1)
    print(f"E = median({epochs}) = {E} -> {out / 'choose_e.json'}", flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["logo", "fit", "cross", "choose_e"])
    ap.add_argument("clips_dir"); ap.add_argument("out_dir")
    ap.add_argument("--films", nargs="+"); ap.add_argument("--train", nargs="+"); ap.add_argument("--test", nargs="+")
    ap.add_argument("--epochs", type=int, default=18)
    ap.add_argument("--save"); ap.add_argument("--save-dir")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", nargs="+", type=int, default=None,
                    help="LOGO default 0 1 2; fit default 0 1 2 3 4; choose_e uses --seed only (0)")
    # Spec-52 defaults; old behaviour only via these flags
    ap.add_argument("--strong-aug", action="store_true", help="old stronger aug (default: soft R4)")
    ap.add_argument("--permutation", action="store_true", help="old np.random.permutation (default: WeightedRandomSampler)")
    ap.add_argument("--ce-class-weights", action="store_true", help="old CE class weights (default: plain CE)")
    ap.add_argument("--use-scaler", action="store_true", help="old GradScaler (default: bf16 direct opt.step)")
    a = ap.parse_args()
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    soft_aug = not a.strong_aug
    use_sampler = not a.permutation
    class_weights = a.ce_class_weights
    use_scaler = a.use_scaler
    train_kw = dict(soft_aug=soft_aug, use_sampler=use_sampler, class_weights=class_weights, use_scaler=use_scaler)
    res = {}
    t0 = time.time()
    if a.mode == "choose_e":
        choose_e(a.clips_dir, a.films, out, max_epochs=a.epochs, seed=a.seed, soft_aug=soft_aug)
        res["seconds"] = time.time() - t0
        json.dump(res, open(out / "choose_e_report.json", "w"), indent=1)
        return
    if a.mode == "logo":
        seeds = a.seeds if a.seeds is not None else [0, 1, 2]
        X, Y, T, Fm = load(a.clips_dir, a.films)
        # Spec 52d: R4 head, no seq
        PM = np.zeros((len(seeds), len(Y), 3), np.float32)
        for si, seed in enumerate(seeds):
            print(f"== logo seed {seed}", flush=True)
            for f in a.films:
                print(f"-- hold out {f} seed {seed}", flush=True)
                tr, te = Fm != f, Fm == f
                m = train(X[tr], Y[tr], epochs=a.epochs, seed=seed, seq=None, **train_kw)
                P = predict(m, X[te], bs=PREDICT_BS, seq=None); PM[si, te] = P
                res.setdefault(f, {})[f"seed{seed}"] = report(f"{f}/seed{seed}", Y[te], P)
                del m; torch.cuda.empty_cache()
        allP = PM.mean(0)
        for f in a.films:
            res[f]["ensemble"] = report(f"{f}/ensemble", Y[Fm == f], allP[Fm == f])
        res["pooled"] = report("pooled", Y, allP)
        np.savez(out / "logo_preds.npz", P=allP, PM=PM, Y=Y, T=T, F=Fm, seeds=np.array(seeds))
    elif a.mode == "cross":
        Xtr, Ytr, Ttr, Ftr = load(a.clips_dir, a.train)
        Xte, Yte, Tte, Fte = load(a.clips_dir, a.test)
        del Ttr, Ftr
        m = train(Xtr, Ytr, epochs=a.epochs, seed=a.seed, seq=None, **train_kw)
        P = predict(m, Xte, bs=PREDICT_BS, seq=None)
        for f in a.test:
            res[f] = report(f, Yte[Fte == f], P[Fte == f])
        res["pooled"] = report("pooled", Yte, P)
        np.savez(out / "cross_preds.npz", P=P, Y=Yte, T=Tte, F=Fte)
    else:  # fit
        seeds = a.seeds if a.seeds is not None else [0, 1, 2, 3, 4]
        X, Y, T, Fm = load(a.clips_dir, a.films)
        del T, Fm
        save_dir = Path(a.save_dir) if a.save_dir else out
        save_dir.mkdir(parents=True, exist_ok=True)
        for seed in seeds:
            print(f"== fit seed {seed}", flush=True)
            m = train(X, Y, epochs=a.epochs, seed=seed, seq=None, **train_kw)
            path = save_dir / f"model_seed{seed}.pt"
            if a.save and len(seeds) == 1:
                path = Path(a.save)
            torch.save(m.state_dict(), path); print("saved", path)
            del m; torch.cuda.empty_cache()
    res["seconds"] = time.time() - t0
    json.dump(res, open(out / f"{a.mode}_report.json", "w"), indent=1)


if __name__ == "__main__":
    main()
