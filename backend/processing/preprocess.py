"""Preprocessing: grayscale, denoise, threshold, deskew."""
from __future__ import annotations
import cv2
import numpy as np


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def denoise(gray: np.ndarray) -> np.ndarray:
    # Non-local means is accurate but slow; use fastNlMeans on small images only
    if gray.size < 3_000_000:
        return cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    return cv2.bilateralFilter(gray, 5, 55, 55)


def binarize(gray: np.ndarray) -> np.ndarray:
    """Adaptive + Otsu combo: pick whichever has more balanced ink ratio."""
    # Adaptive
    ada = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 10)
    # Otsu
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    def ink_ratio(x):
        return (x > 0).sum() / x.size

    r_ada = ink_ratio(ada)
    r_otsu = ink_ratio(otsu)
    # Drawings usually have 2%-25% ink; pick closer to 10%
    if abs(r_ada - 0.08) <= abs(r_otsu - 0.08):
        return ada
    return otsu


def detect_skew_angle(binary: np.ndarray) -> float:
    """Estimate skew via minAreaRect on ink pixels."""
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 500:
        return 0.0
    # Sample to speed up
    if len(coords) > 50000:
        idx = np.random.choice(len(coords), 50000, replace=False)
        coords = coords[idx]
    rect = cv2.minAreaRect(coords.astype(np.float32))
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90
    # Clamp to reasonable range
    if abs(angle) > 30:
        return 0.0
    return float(angle)


def deskew(img: np.ndarray, angle: float | None = None) -> tuple[np.ndarray, float]:
    gray = to_gray(img)
    if angle is None:
        bw = binarize(gray)
        angle = detect_skew_angle(bw)
    if abs(angle) < 0.2:
        return img, 0.0
    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated, float(angle)


def preprocess(img: np.ndarray) -> dict:
    """Full preprocess. Returns dict with original, gray, binary, deskewed etc."""
    gray = to_gray(img)
    deskewed, angle = deskew(img)
    gray_ds = to_gray(deskewed)
    den = denoise(gray_ds)
    binary = binarize(den)
    # Clean up small noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary_clean = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    return {
        "deskewed": deskewed,
        "gray": gray_ds,
        "binary": binary_clean,
        "rotation": angle,
    }
