#!/usr/bin/env python3
"""Cluster v37 features (gap + interpolated) and compare against v35."""
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, SpectralClustering
from sklearn.decomposition import PCA
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

CSV_IN  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v37.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v37_clustered.csv'
PNG_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/cluster_v37_pca.png'

FEATURE_COLS = [
    'interp_growth', 'interp_width', 'interp_turn', 'interp_angle_var',
    'interp_mean_conf',
    'mean_gap_len', 'max_gap_len', 'visibility_ratio',
    'pre_anchor_visibility', 'post_anchor_visibility',
    'trajectory_certainty', 'corridor_certainty',
    'origin_lateral_ft', 'origin_distance_ft', 'corridor_stability',
]


def main():
    df = pd.read_csv(CSV_IN)
    print("Loaded {} rows".format(len(df)))

    # Fill NaN
    for c in FEATURE_COLS:
        if c in df.columns:
            df[c] = df[c].fillna(df[c].median())

    X = df[FEATURE_COLS].values.astype(float)

    # Normalize
    scaler = StandardScaler()
    Xn = scaler.fit_transform(X)

    # PCA
    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(Xn)
    print("PCA explained variance: {}".format(pca.explained_variance_ratio_.round(3)))

    # Clustering
    results = {}
    for k in [2, 3, 4]:
        km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(Xn)
        df['km{}'.format(k)] = km.labels_
        results['km{}'.format(k)] = km.labels_

    k_spec = min(3, len(Xn))
    if k_spec >= 2:
        nn = min(5, len(Xn) - 1)
        spec = SpectralClustering(n_clusters=k_spec, random_state=42,
                                   affinity='nearest_neighbors',
                                   n_neighbors=nn).fit(Xn)
        df['spectral'] = spec.labels_
        results['spectral'] = spec.labels_

    # Summaries
    for method, labels in results.items():
        print("\n=== {} ===".format(method))
        for lbl in sorted(set(labels)):
            sub = df[labels == lbl]
            frames = ', '.join('F{}'.format(int(f)) for f in sub['frame'].values)
            print("  Cluster {}: n={} | {}".format(lbl, len(sub), frames))
            for c in ['interp_growth', 'interp_width', 'interp_turn', 'interp_angle_var',
                       'visibility_ratio', 'trajectory_certainty',
                       'origin_lateral_ft', 'origin_distance_ft']:
                if c in sub.columns:
                    vals = sub[c].dropna()
                    if len(vals) > 0:
                        print("    {}: mean={:.2f} median={:.2f}".format(c, vals.mean(), vals.median()))

    # Compare with v35 clusters
    print("\n=== Cluster Comparison: v35 km3 vs v37 km3 ===")
    if 'km3' in df.columns:
        v35_clusters = df['km3'].values if 'km3' in df.columns else None
        v37_clusters = df['km3'].values
        for i in range(len(df)):
            f = int(df.iloc[i]['frame'])
            v35c = int(df.iloc[i].get('km3_y', df.iloc[i]['km3'])) if 'km3_y' in df.columns else '?'
            v37c = int(df.iloc[i]['km3'])
            match = 'SAME' if str(v35c) == str(v37c) else 'CHANGED'
            print("  F{}: v35=C{} -> v37=C{} [{}]".format(f, v35c, v37c, match))

    # Visualization
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle('v37 Clustering (gap + interp features)', fontsize=14, fontweight='bold')

    for ax, method in zip(axes, ['km2', 'km3', 'spectral']):
        if method not in results:
            continue
        labels = results[method]
        for lbl in sorted(set(labels)):
            m = labels == lbl
            nm = 'C{}'.format(lbl)
            ax.scatter(X_pca[m, 0], X_pca[m, 1], label=nm, s=120, alpha=0.7, edgecolors='k')
            for idx in np.where(m)[0]:
                row = df.iloc[idx]
                ax.annotate('F{}'.format(int(row['frame'])),
                           (X_pca[idx, 0], X_pca[idx, 1]),
                           fontsize=8, ha='center', va='bottom')
        ax.set_xlabel('PC1 ({:.0%})'.format(pca.explained_variance_ratio_[0]))
        ax.set_ylabel('PC2 ({:.0%})'.format(pca.explained_variance_ratio_[1]))
        ax.set_title(method)
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(PNG_OUT, dpi=150)
    print("\nSaved to {}".format(PNG_OUT))

    df.to_csv(CSV_OUT, index=False)
    print("Saved clustered features to {}".format(CSV_OUT))


if __name__ == '__main__':
    main()
