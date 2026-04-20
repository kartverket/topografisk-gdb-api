class FeatureNotFoundError(Exception):
    def __init__(self):
        super().__init__("Feature not found")
