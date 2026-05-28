#!/usr/bin/env python3
"""Cluster basketball shot features to identify natural shot regimes.

Reads shot_features_v34.csv and runs:
  - K-means (k=3,4,5)
  - HDBSCAN (density-based)
  - PCA projection
Outputs cluster labels + visualizations.
"""
import sys
sys.path.insert(0, '/home/monk-admin/PROJECTS/liberty-basketball-analysis')

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, SpectralClustering
from sklearn.decomposition import PCA
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

FEATURE_COLS = [
    'origin_distance_ft',
    'origin_lateral_ft',
    'corridor_stability',
    'emergence_angle',
    'anchor_confidence',
    'emergence_n_points',
]

CSV_IN  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v34.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v34_clustered.csv'
PNG_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/cluster_scatter.png'


def main():
    df = pd.read_csv(CSV_IN)
    print(f"Loaded {len(df)} rows")

    # Keep only rows with valid feature data (have emergence features)
    mask = df['emergence_n_points'].notna() & (df['emergence_n_points'] > 0)
    df_valid = df[mask].copy()
    print(f"Valid emergence rows: {len(df_valid)}")

    if len(df_valid) < 5:
        print("ERROR: too few valid rows for clustering")
        return

    # Fill any remaining NaN with column median
    for c in FEATURE_COLS:
        if df_valid[c].isna().any():
            med = df_valid[c].median()
            df_valid[c] = df_valid[c].fillna(med)

    X = df_valid[FEATURE_COLS].values.astype(float)

    # --- Normalize ---
    scaler = StandardScaler()
    Xn = scaler.fit_transform(X)

    # --- PCA for visualization ---
    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(Xn)
    print(f"PCA explained variance: {pca.explained_variance_ratio_.round(3)}")

    # --- K-means k=3 ---
    km3 = KMeans(n_clusters=3, random_state=42, n_init=20).fit(Xn)
    df_valid['km3'] = km3.labels_

    # --- K-means k=4 ---
    km4 = KMeans(n_clusters=4, random_state=42, n_init=20).fit(Xn)
    df_valid['km4'] = km4.labels_

    # --- HDBSCAN ---
    try:
        import hdbscan
        hdb = hdbscan.HDBSCAN(min_cluster_size=3, min_samples=2).fit(Xn)
        df_valid['hdbscan'] = hdb.labels_
        n_hdb = len(set(hdb.labels_)) - (1 if -1 in hdb.labels_ else 0)
        print(f"HDBSCAN: {n_hdb} clusters + noise")
    except ImportError:
        print("hdbscan not installed, skipping HDBSCAN")
        df_valid['hdbscan'] = -1

    # --- Spectral ---
    spec = SpectralClustering(n_clusters=3, random_state=42, affinity='nearest_neighbors', n_neighbors=min(5, len(Xn)-1)).fit(Xn)
    df_valid['spectral'] = spec.labels_

    # --- Print summaries ---
    for method, col in [('K-means k=3', 'km3'), ('K-means k=4', 'km4'), ('Spectral k=3', 'spectral'), ('HDBSCAN', 'hdbscan')]:
        print(f"\n=== {method} ===")
        labels = df_valid[col].values
        for lbl in sorted(set(labels)):
            sub = df_valid[df_valid[col] == lbl]
            makes = (sub['make_miss'] == 'MAKE').sum()
            framestr = ', '.join(f"F{int(f)}" for f in sub['frame'].values[:8])
            if len(sub) > 8:
                framestr += f'... (+{len(sub)-8})'
            avg_dist = sub['origin_distance_ft'].mean()
            avg_lat  = sub['origin_lateral_ft'].mean()
            avg_stab = sub['corridor_stability'].mean()
            avg_pts  = sub['emergence_n_points'].mean()
            print(f"  Cluster {lbl}: n={len(sub)} | makes={makes} | "
                  f"dist={avg_dist:.1f}ft | lat={avg_lat:.1f}ft | "
                  f"stab={avg_stab:.2f} | pts={avg_pts:.1f} | frames=[{framestr}]")

    # --- Save ---
    df_valid.to_csv(CSV_OUT, index=False)
    print(f"\nSaved clustered features to {CSV_OUT}")

    # --- Visualization ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle('Shot Feature Clustering', fontsize=14, fontweight='bold')

    for ax, col, title in [
        (axes[0,0], 'km3', 'K-means (k=3)'),
        (axes[0,1], 'km4', 'K-means (k=4)'),
        (axes[1,0], 'spectral', 'Spectral (k=3)'),
        (axes[1,1], 'hdbscan', 'HDBSCAN'),
    ]:
        labels = df_valid[col].values
        for lbl in sorted(set(labels)):
            m = labels == lbl
            lbl_name = f'Noise' if lbl == -1 else f'C{lbl}'
            ax.scatter(X_pca[m, 0], X_pca[m, 1], label=lbl_name, s=80, alpha=0.7)
            # Annotate with frame numbers
            for idx in np.where(m)[0]:
                row = df_valid.iloc[idx]
                ax.annotate(f"F{int(row['frame'])}", (X_pca[idx, 0], X_pca[idx, 1]),
                           fontsize=7, alpha=0.6, ha='center', va='bottom')
        ax.set_xlabel('PC1')
        ax.set_ylabel('PC2')
        ax.set_title(title)
        ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(PNG_OUT, dpi=150)
    print(f"Saved visualization to {PNG_OUT}")


if __name__ == '__main__':
    main()
