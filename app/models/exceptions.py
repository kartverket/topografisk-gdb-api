class FeatureNotFoundError(Exception):
    def __init__(self):
        super().__init__("Feature not found")


class InvalidBoundingBoxError(Exception):
    def __init__(self, bbox: str):
        super().__init__(
            f"Invalid bounding box. Expected format 0.0,0.0,10.0,10.0 but was {bbox}"
        )
