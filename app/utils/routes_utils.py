def bbox_is_valid(bbox: str) -> bool:
    BBOX_ARRAY_SIZE = 4

    bbox_is_valid = True
    if bbox is not None:
        bbox_array = bbox.split(",")
        if len(bbox_array) is not BBOX_ARRAY_SIZE:
            bbox_is_valid = False
        for coord in bbox_array:
            try:
                float(coord)
            except ValueError:
                bbox_is_valid = False
    return bbox_is_valid
