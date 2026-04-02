from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

DEFAULT_TEXT_SVD_COMPONENTS = 10
DEFAULT_TEXT_MAX_FEATURES = 1000
DEFAULT_TEXT_MIN_DF = 2
DEFAULT_TEXT_MAX_CHARS = 2000


@dataclass
class TextSVDArtifacts:
    """Artifacts required to transform text into fixed SVD features."""

    vectorizer: TfidfVectorizer
    svd: TruncatedSVD
    n_components: int


def get_text_svd_columns(n_components: int = DEFAULT_TEXT_SVD_COMPONENTS) -> list[str]:
    """Return deterministic text SVD feature names."""

    return [f"text_svd_{i}" for i in range(n_components)]


def _normalize_text_series(text: pd.Series) -> pd.Series:
    """Normalize text input before TF-IDF vectorization."""

    return (
        pd.Series(text)
        .fillna("")
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.slice(0, DEFAULT_TEXT_MAX_CHARS)
    )


def _zero_text_features(index: pd.Index, n_components: int) -> pd.DataFrame:
    """Return an all-zero text feature frame with deterministic columns."""

    return pd.DataFrame(0.0, index=index, columns=get_text_svd_columns(n_components))


def fit_text_svd_features(
    train_text: pd.Series,
    transform_text: pd.Series | None = None,
    *,
    n_components: int = DEFAULT_TEXT_SVD_COMPONENTS,
    max_features: int = DEFAULT_TEXT_MAX_FEATURES,
    min_df: int = DEFAULT_TEXT_MIN_DF,
) -> tuple[pd.DataFrame, pd.DataFrame | None, TextSVDArtifacts | None]:
    """Fit TF-IDF + SVD on training text and transform training/optional inference text.

    Returns fixed-width feature matrices even when the corpus is too sparse by
    falling back to all-zero columns.
    """

    train_series = _normalize_text_series(train_text)
    transform_series = (
        _normalize_text_series(transform_text) if transform_text is not None else None
    )

    train_zero = _zero_text_features(train_series.index, n_components)
    transform_zero = (
        _zero_text_features(transform_series.index, n_components)
        if transform_series is not None
        else None
    )

    try:
        vectorizer = TfidfVectorizer(
            max_features=max_features,
            min_df=min_df,
            ngram_range=(1, 1),
            sublinear_tf=True,
            stop_words="english",
            dtype=np.float32,
        )
        tfidf_train = vectorizer.fit_transform(train_series.tolist())
    except ValueError:
        return train_zero, transform_zero, None

    effective_components = min(
        n_components,
        max(tfidf_train.shape[0] - 1, 0),
        max(tfidf_train.shape[1] - 1, 0),
    )
    if effective_components < 1:
        return train_zero, transform_zero, None

    svd = TruncatedSVD(n_components=effective_components, random_state=42)
    train_matrix = svd.fit_transform(tfidf_train)

    train_out = train_zero.copy()
    train_out.iloc[:, :effective_components] = train_matrix

    artifacts = TextSVDArtifacts(
        vectorizer=vectorizer,
        svd=svd,
        n_components=n_components,
    )

    transform_out = None
    if transform_series is not None:
        transform_out = transform_text_svd_features(transform_series, artifacts)

    return train_out, transform_out, artifacts


def transform_text_svd_features(
    text: pd.Series,
    artifacts: TextSVDArtifacts | None,
) -> pd.DataFrame:
    """Transform text using existing TF-IDF + SVD artifacts."""

    series = _normalize_text_series(text)
    out = _zero_text_features(
        series.index, DEFAULT_TEXT_SVD_COMPONENTS if artifacts is None else artifacts.n_components
    )

    if artifacts is None:
        return out

    tfidf = artifacts.vectorizer.transform(series.tolist())
    matrix = artifacts.svd.transform(tfidf)
    out.iloc[:, : matrix.shape[1]] = matrix
    return out
