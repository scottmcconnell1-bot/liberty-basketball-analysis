"""
Training script for candidate ball weights on the Notus dataset.
Complies with AGENT_OPERATIONAL_PROTOCOL.md:
- Uses dataset: C:\\Users\\scott\\AppData\\Local\\Temp\\ball_net_ds_notus7\\data.yaml
- Starts from v6 weights: C:\\Users\\scott\\AppData\\Local\\Temp\\ball_net_runs\\v6\\weights\\best.pt
- Muse recipe: 20 epochs, freeze first 10 layers, lr0=0.0005, batch=8, imgsz=640, device='cpu', workers=2
- Fixes optimizer override by explicitly setting optimizer='SGD' to strictly honor lr0=0.0005.
- Saves output to: C:\\Users\\scott\\Documents\\liberty-basketball-analysis\\models\\candidate_notus_net.pt
"""
from pathlib import Path
import sys
from ultralytics import YOLO

def train_candidate():
    print("=" * 70)
    print("       CANDIDATE NOTUS WEIGHTS TRAINING SCRIPT (MUSE RECIPE)     ")
    print("=" * 70)

    # Define paths using raw strings or Path objects for Windows compatibility
    data_yaml = Path(r"C:\Users\scott\AppData\Local\Temp\ball_net_ds_notus7\data.yaml")
    base_weights = Path(r"C:\Users\scott\AppData\Local\Temp\ball_net_runs\v6\weights\best.pt")
    output_weights_dir = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis\models")
    output_weights_dir.mkdir(parents=True, exist_ok=True)
    final_output_path = output_weights_dir / "candidate_notus_net.pt"

    # Validate input paths exist before starting training (non-silent exit on failure)
    if not data_yaml.exists():
        print(f"[ERROR] Dataset configuration not found at: {data_yaml}")
        sys.exit(1)
    if not base_weights.exists():
        print(f"[ERROR] Base weights not found at: {base_weights}")
        sys.exit(1)

    print(f"[INFO] Loading base model from: {base_weights}")
    model = YOLO(str(base_weights))

    print("[INFO] Starting training with Muse recipe parameters...")
    print(f"  - Epochs: 20")
    print(f"  - Frozen Layers: 10")
    print(f"  - Initial Learning Rate (lr0): 0.0005")
    print(f"  - Optimizer: SGD (Explicitly pinned to prevent auto-override)")
    print(f"  - Batch Size: 8")
    print(f"  - Image Size: 640")
    print(f"  - Device: 0")
    print(f"  - Workers: 2")
    print(f"  - Dataset YAML: {data_yaml}")

    # Execute training following the exact Muse recipe with explicit optimizer
    results = model.train(
        data=str(data_yaml),
        epochs=20,
        freeze=10,
        lr0=0.0005,
        optimizer='SGD',
        batch=8,
        imgsz=640,
        device='cpu',
        workers=2,
        verbose=True
    )

    # Ultralytics saves the best weights in its training run directory.
    trained_best_path = Path(model.trainer.save_dir) / "weights" / "best.pt"
    
    if trained_best_path.exists():
        import shutil
        shutil.copy(trained_best_path, final_output_path)
        print(f"\n[SUCCESS] Candidate weights successfully saved to: {final_output_path.resolve()}")
    else:
        print(f"\n[ERROR] Training completed, but expected output weights not found at {trained_best_path}.")
        sys.exit(1)

    print("=" * 70)

if __name__ == "__main__":
    train_candidate()
