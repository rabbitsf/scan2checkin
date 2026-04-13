"""
Pre-warm PaddleOCR models during Docker build so first requests are fast.
Run once at build time — not used at runtime.
"""
try:
    from paddleocr import PaddleOCR
    PaddleOCR(use_angle_cls=True, lang="en")
    print("PaddleOCR models pre-warmed successfully.")
except Exception as e:
    # Don't fail the build if model download is unavailable in the build environment.
    # Models will download on first request instead.
    print(f"PaddleOCR pre-warm skipped: {e}")
