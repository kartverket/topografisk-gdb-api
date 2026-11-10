# Domain document

The domain document is a YAML file which is one of the two required inputs
(the other being a UML document) for the converter which generates the
dataset description.

The `general` mapping must define `srid` and `has_z`. `outward_identifier`
and `server_managed` can be defined for either the entire dataset under
`general` or for each specific collection. The following is an example of
a domain file:

```yaml
general:
  srid: 5973
  has_z: true
  server_managed:
    identifikasjon.versjonid: timestamp_iso
collections:
  spormidt:
    outward_identifier: identifikasjon.lokalid
```

Collection keys are normalized collection names. A collection-level
`outward_identifier` or `server_managed` cannot be specified alongside the
same key in `general`; doing so raises `ValueError`.
