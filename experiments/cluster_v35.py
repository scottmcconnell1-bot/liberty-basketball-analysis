#!/usr/bin/env python3
"""Cluster enriched v35 shot features: growth, width, turn, angle_var, decay, lateral, dist_ft.

Runs K-means (k=2,3,4), HDBSCAN, Spectral, PCA.
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, SpectralClustering
from sklearn.decomposition import PCA
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

CSV_IN  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v35.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v35_clustered.csv'
PNG_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/cluster_v35_pca.png'
PNG_HM  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/cluster_v35_heatmap.png'

FEATURE_COLS = [
    'growth', 'width', 'turn', 'angle_var', 'decay',
    'origin_lateral_ft', 'origin_distance_ft', 'corridor_stability',
    'emergence_n_points',
]


def main():
    df = pd.read_csv(CSV_IN)
    print(f"Loaded {len(df)} rows")

    # Fill NaN
    for c in FEATURE_COLS:
        if c in df.columns:
            df[c] = df[c].fillna(df[c].median())

    X = df[FEATURE_COLS].values.astype(float)
    print(f"Feature matrix: {X.shape}")

    # Normalize
    scaler = StandardScaler()
    Xn = scaler.fit_transform(X)

    # PCA
    pca = PCA(n_components=min(5, X.shape[1]))
    X_pca = pca.fit_transform(Xn)
    print(f"PCA explained variance: {pca.explained_variance_ratio_.round(3)}")

    # --- Clustering ---
    results = {}

    # K-means k=2,3,4
    for k in [2, 3, 4]:
        km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(Xn)
        df[f'km{k}'] = km.labels_
        results[f'km{k}'] = km.labels_

    # HDBSCAN
    try:
        import hdbscan
        hdb = hdbscan.HDBSCAN(min_cluster_size=3, min_samples=2).fit(Xn)
        df['hdbscan'] = hdb.labels_
        results['hdbscan'] = hdb.labels_
        n_clusters = len(set(hdb.labels_)) - (1 if -1 in hdb.labels_ else 0)
        print(f"HDBSCAN: {n_clusters} clusters, {(hdb.labels_ == -1).sum()} noise")
    except ImportError:
        print("hdbscan not installed")

    # Spectral
    k_spec = min(3, len(Xn))
    if k_spec >= 2:
        nn = min(5, len(Xn) - 1)
        spec = SpectralClustering(n_clusters=k_spec, random_state=42,
                                   affinity='nearest_neighbors',
                                   n_neighbors=nn).fit(Xn)
        df['spectral'] = spec.labels_
        results['spectral'] = spec.labels_

    # --- Summaries ---
    for method, labels in results.items():
        print(f"\n=== {method} ===")
        for lbl in sorted(set(labels)):
            sub = df[labels == lbl]
            makes = (sub['make_miss'] == 'MAKE').sum()
            frames = ', '.join(f"F{int(f)}" for f in sub['frame'].values)
            print(f"  Cluster {lbl}: n={len(sub)} makes={makes} | {frames}")
            for c in ['growth', 'width', 'turn', 'angle_var',
                       'origin_lateral_ft', 'origin_distance_ft', 'corridor_stability']:
                if c in sub.columns:
                    vals = sub[c].dropna()
                    if len(vals) > 0:
                        print(f"    {c}: mean={vals.mean():.2f} median={vals.median():.2f} "
                              f"min={vals.min():.2f} max={vals.max():.2f}")

    # --- PCA scatter plot ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle('v35 Feature Clustering (PCA projection)', fontsize=14, fontweight='bold')

    plot_methods = ['km2', 'km3', 'km4', 'spectral']
    for ax, method in zip(axes.flat, plot_methods):
        if method not in results:
            continue
        labels = results[method]
        for lbl in sorted(set(labels)):
            m = labels == lbl
            nm = f'Noise' if lbl == -1 else f'C{lbl}'
            ax.scatter(X_pca[m, 0], X_pca[m, 1], label=nm, s=120, alpha=0.7, edgecolors='k')
            for idx in np.where(m)[0]:
                row = df.iloc[idx]
                ax.annotate(f"F{int(row['frame'])}",
                           (X_pca[idx, 0], X_pca[idx, 1]),
                           fontsize=8, ha='center', va='bottom', fontweight='bold')
        ax.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]:.0%})')
        ax.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]:.0%})')
        ax.set_title(method)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(PNG_OUT, dpi=150)
    print(f"\nSaved scatter plot to {PNG_OUT}")

    # --- Feature heatmap by cluster (k=3) ---
    if 'km3' in df.columns:
        fig, ax = plt.subplots(figsize=(14, 6))
        cluster_means = df.groupby('km3')[FEATURE_COLS].mean()
        # Z-score within each feature
        for c in FEATURE_COLS:
            col = cluster_means[c]
            if col.std() > 0:
                cluster_means[c] = (col - col.mean()) / col.std()
        im = ax.imshow(cluster_means.values, aspect='auto', cmap='RdYlBu_r')
        ax.set_xticks(range(len(FEATURE_COLS)))
        ax.set_xticklabels(FEATURE_COLS, rotation=45, ha='right')
        ax.set_yticks(range(len(cluster_means)))
        ax.set_yticklabels([f'Cluster {i}' for i in cluster_means.index])
        for i in range(len(cluster_means)):
            for j in range(len(FEATURE_COLS)):
                ax.text(j, i, f'{cluster_means.values[i,j]:.2f}',
                       ha='center', va='center', fontsize=9)
        plt.colorbar(im, ax=ax, label='z-score')
        ax.set_title('v35 Feature Profiles by K-means Cluster (k=3)')
        plt.tight_layout()
        plt.savefig(PNG_HM, dpi=150)
        print(f"Saved heatmap to {PNG_HM}")

    # Save
    df.to_csv(CSV_OUT, index=False)
    print(f"Saved clustered features to {CSV_OUT}")


if __name__ == '__main__':
    main()
