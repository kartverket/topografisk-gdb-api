def bbox_is_valid(bbox: str) -> bool:
    BBOX_ARRAY_SIZE = 4

    if bbox is None:
        return False
    else:
        bbox_array = bbox.split(",")
        if len(bbox_array) is not BBOX_ARRAY_SIZE:
            return False
        for coord in bbox_array:
            try:
                float(coord)
            except ValueError:
                return False

    return True
