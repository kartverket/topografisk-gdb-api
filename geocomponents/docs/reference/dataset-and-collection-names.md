# Dataset, collection, and field names

The `name` of a dataset, collection, field (including each nested field), or code list starts with an ASCII letter, `æ`, `ø`, `å` (in either case), or `_`. Subsequent characters may also be ASCII digits. Names retain their original spelling, including camelCase and Norwegian letters. Hyphens, spaces, and other characters are invalid.

Each name is limited to 40 UTF-8 bytes. Generated PostgreSQL object names must fit in 63 UTF-8 bytes.

Names that differ only by case are not allowed in the same scope: datasets across description files, collections or code lists within a dataset, and fields within one collection or nested object. The same field name may be used in different collections or objects. Relationship property names cannot conflict with fields in their collection. Collection names cannot conflict with process IDs in the same dataset.

`ogc` and `topogdb` are reserved dataset names. `association`, `association_role`, and `collection_capability` are reserved collection names. `id` and `geometry` are reserved top-level field names. These checks ignore case.

PostgreSQL tables and columns use the accepted names verbatim. SQL references quote them to preserve their spelling.
