"""Black-box DB contract for ``ogc.transaction``.

These tests call ONLY the public ``ogc.*`` database functions with OGC
identifiers ``(dataset, collection)`` and observe state through
``ogc.feature_item``. They pin the atomic transaction contract rather than any
table layout or generated internal function names.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import orjson
import psycopg

_GEOM = {
    "Point": {"type": "Point", "coordinates": [10, 55]},
    "MultiPoint": {"type": "MultiPoint", "coordinates": [[10, 55]]},
    "LineString": {"type": "LineString", "coordinates": [[10, 55], [11, 56]]},
    "MultiLineString": {
        "type": "MultiLineString",
        "coordinates": [[[10, 55], [11, 56]]],
    },
    "Polygon": {
        "type": "Polygon",
        "coordinates": [[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]],
    },
    "MultiPolygon": {
        "type": "MultiPolygon",
        "coordinates": [[[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]]],
    },
}
_DEFAULT_GEOMETRY = object()


@dataclass(frozen=True)
class _MixedParcelSetup:
    before: dict[UUID, dict]
    document: dict
    failing_item: dict
    insert_id: UUID
    update_id: UUID
    replace_id: UUID
    delete_id: UUID
    rejected_id: UUID


def _value(sql_type, variant=0):
    s = sql_type.lower()
    if s == "integer":
        return 1 + variant
    if s in ("double precision", "real", "numeric"):
        return 1.0 + variant
    if s == "boolean":
        return variant == 0
    if s in ("timestamptz", "timestamp with time zone", "timestamp"):
        return "2026-01-01T00:00:00Z" if variant == 0 else "2026-02-01T00:00:00Z"
    if s == "date":
        return "2026-01-01" if variant == 0 else "2026-02-01"
    return "x" if variant == 0 else "y"


def _field_value(f, variant=0):
    if f.codelist_values:
        return f.codelist_values[variant % len(f.codelist_values)]
    if f.sql_type == "jsonb":
        return {sf.name: _field_value(sf, variant) for sf in f.sub_fields}
    return _value(f.sql_type, variant)


def _sample_feature(coll, *, geometry=_DEFAULT_GEOMETRY, properties=None, fid=None):
    props = {
        f.name: _field_value(f)
        for f in coll.fields
        if f.required and not f.auto_increment
    }
    if any(f.name == "source" for f in coll.fields):
        props["source"] = "orig"
    if properties:
        props.update(properties)
    feature = {
        "type": "Feature",
        "properties": props,
    }
    if fid is not None:
        feature["id"] = str(fid)
    feature["geometry"] = (
        _GEOM[coll.geometry_type] if geometry is _DEFAULT_GEOMETRY else geometry
    )
    return feature


def _malformed_geometry(coll):
    return {"type": coll.geometry_type, "coordinates": "nonsense"}


def _collection(datasets, dataset_name, collection_name):
    for dataset in datasets:
        if dataset.name != dataset_name:
            continue
        for collection in dataset.collections:
            if collection.name == collection_name:
                return collection
    raise AssertionError(f"missing collection {dataset_name}.{collection_name}")


def _item(cur, ds, coll, fid):
    cur.execute("select ogc.feature_item(%s,%s,%s)", (ds, coll, fid))
    return cur.fetchone()[0]


def _create(cur, ds, coll, feature):
    cur.execute(
        "select ogc.feature_create(%s,%s,%s)",
        (ds, coll, orjson.dumps(feature).decode()),
    )
    return cur.fetchone()[0]


def _delete(cur, ds, coll, fid):
    cur.execute("select ogc.feature_delete(%s,%s,%s)", (ds, coll, fid))
    return cur.fetchone()[0]


def _transaction(cur, dataset, document):
    cur.execute(
        "select ogc.transaction(%s,%s)",
        (dataset, orjson.dumps(document).decode()),
    )
    return cur.fetchone()[0]


def _remove_feature(cur, dataset_name, coll, fid):
    if coll.supports_crud:
        assert _delete(cur, dataset_name, coll.name, fid) is True
        return

    report = _transaction(
        cur,
        dataset_name,
        {
            "semantic": "atomic",
            "transaction": [
                {
                    "action": "delete",
                    "collection": coll.name,
                    "id": str(fid),
                }
            ],
        },
    )
    assert report["committed"] is True


def _assert_report_shell(report, *, committed, item_count):
    assert set(report) == {
        "committed",
        "phase",
        "reason",
        "items",
        "structure",
        "geometry",
    }
    assert report["committed"] is committed
    assert report["phase"] == "items"
    assert report["reason"] is None
    assert report["structure"] == []
    assert report["geometry"] == []
    assert len(report["items"]) == item_count


def _assert_item_keys(item):
    assert set(item) == {
        "index",
        "action",
        "collection",
        "id",
        "status",
        "sqlstate",
        "reason",
    }


def _assert_committed_item(item, expected):
    _assert_item_keys(item)
    assert item["index"] == expected["index"]
    assert item["action"] == expected["action"]
    assert item["collection"] == expected["collection"]
    assert item["id"] == str(expected["id"])
    assert item["status"] == expected["status"]
    assert item["sqlstate"] is None
    assert item["reason"] is None


def _assert_rejected_item(item, expected):
    _assert_item_keys(item)
    assert item["index"] == expected["index"]
    assert item["action"] == expected["action"]
    assert item["collection"] == expected["collection"]
    assert item["id"] == (str(expected["id"]) if expected["id"] is not None else None)
    assert item["status"] == "rejected"
    assert item["sqlstate"] == expected["sqlstate"]
    assert isinstance(item["reason"], str)
    assert item["reason"]


def _mixed_parcel_setup(cur, datasets):
    coll = _collection(datasets, "cadastre", "parcels")
    update_id = _create(
        cur,
        "cadastre",
        "parcels",
        _sample_feature(coll, properties={"label": "before-update", "area_m2": 10.0}),
    )
    replace_id = _create(
        cur,
        "cadastre",
        "parcels",
        _sample_feature(
            coll,
            properties={"label": "before-replace", "status": "active", "area_m2": 20.0},
        ),
    )
    delete_id = _create(
        cur,
        "cadastre",
        "parcels",
        _sample_feature(coll, properties={"label": "before-delete", "area_m2": 30.0}),
    )
    before = {
        update_id: _item(cur, "cadastre", "parcels", update_id),
        replace_id: _item(cur, "cadastre", "parcels", replace_id),
        delete_id: _item(cur, "cadastre", "parcels", delete_id),
    }
    insert_id = uuid4()
    rejected_id = uuid4()
    document = {
        "semantic": "atomic",
        "transaction": [
            {
                "action": "insert",
                "collection": "parcels",
                "feature": _sample_feature(
                    coll,
                    fid=insert_id,
                    properties={"label": "inserted", "area_m2": 40.0},
                ),
            },
            {
                "action": "update",
                "collection": "parcels",
                "id": str(update_id),
                "feature": {"properties": {"label": "after-update"}},
            },
            {
                "action": "replace",
                "collection": "parcels",
                "id": str(replace_id),
                "feature": _sample_feature(
                    coll,
                    properties={
                        "label": "after-replace",
                        "status": "retired",
                        "area_m2": 50.0,
                    },
                ),
            },
            {
                "action": "delete",
                "collection": "parcels",
                "id": str(delete_id),
            },
        ],
    }
    failing_item = {
        "action": "insert",
        "collection": "parcels",
        "feature": _sample_feature(
            coll,
            fid=rejected_id,
            geometry=_malformed_geometry(coll),
            properties={"label": "bad-geometry", "area_m2": 60.0},
        ),
    }
    return _MixedParcelSetup(
        before=before,
        document=document,
        failing_item=failing_item,
        insert_id=insert_id,
        update_id=update_id,
        replace_id=replace_id,
        delete_id=delete_id,
        rejected_id=rejected_id,
    )


def test_transaction_mixed_verbs_failure_rolls_back_and_report_matches_state(
    datasets, conn
):
    coll = _collection(datasets, "cadastre", "parcels")

    with conn.cursor() as cur:
        setup = _mixed_parcel_setup(cur, datasets)

        report = _transaction(
            cur,
            "cadastre",
            {
                **setup.document,
                "transaction": [*setup.document["transaction"], setup.failing_item],
            },
        )

        _assert_report_shell(report, committed=False, item_count=1)
        _assert_rejected_item(
            report["items"][0],
            {
                "index": 4,
                "action": "insert",
                "collection": "parcels",
                "id": setup.rejected_id,
                "sqlstate": "XX000",
            },
        )

        assert _item(cur, "cadastre", "parcels", setup.insert_id) is None
        for fid, original in setup.before.items():
            assert _item(cur, "cadastre", "parcels", fid) == original
        for fid in (setup.update_id, setup.replace_id, setup.delete_id):
            _remove_feature(cur, "cadastre", coll, fid)


def test_transaction_mixed_verbs_success_commits_and_report_matches_state(
    datasets, conn
):
    coll = _collection(datasets, "cadastre", "parcels")

    with conn.cursor() as cur:
        setup = _mixed_parcel_setup(cur, datasets)

        report = _transaction(cur, "cadastre", setup.document)

        _assert_report_shell(report, committed=True, item_count=4)
        _assert_committed_item(
            report["items"][0],
            {
                "index": 0,
                "action": "insert",
                "collection": "parcels",
                "id": setup.insert_id,
                "status": "created",
            },
        )
        _assert_committed_item(
            report["items"][1],
            {
                "index": 1,
                "action": "update",
                "collection": "parcels",
                "id": setup.update_id,
                "status": "updated",
            },
        )
        _assert_committed_item(
            report["items"][2],
            {
                "index": 2,
                "action": "replace",
                "collection": "parcels",
                "id": setup.replace_id,
                "status": "updated",
            },
        )
        _assert_committed_item(
            report["items"][3],
            {
                "index": 3,
                "action": "delete",
                "collection": "parcels",
                "id": setup.delete_id,
                "status": "deleted",
            },
        )

        inserted = _item(cur, "cadastre", "parcels", setup.insert_id)
        assert inserted is not None
        assert inserted["id"] == str(setup.insert_id)
        assert inserted["properties"]["label"] == "inserted"

        updated = _item(cur, "cadastre", "parcels", setup.update_id)
        assert updated is not None
        assert updated["properties"]["label"] == "after-update"

        replaced = _item(cur, "cadastre", "parcels", setup.replace_id)
        assert replaced is not None
        assert replaced["properties"]["label"] == "after-replace"
        assert replaced["properties"]["status"] == "retired"

        assert _item(cur, "cadastre", "parcels", setup.delete_id) is None
        for fid in (setup.insert_id, setup.update_id, setup.replace_id):
            _remove_feature(cur, "cadastre", coll, fid)


def test_transaction_failure_rollback_stays_inside_savepoint_scope(
    datasets, conn_non_autocommit
):
    coll = _collection(datasets, "cadastre", "parcels")

    with conn_non_autocommit.cursor() as cur:
        witness_id = _create(
            cur,
            "cadastre",
            "parcels",
            _sample_feature(coll, properties={"label": "outer-write", "area_m2": 70.0}),
        )

        report = _transaction(
            cur,
            "cadastre",
            {
                "semantic": "atomic",
                "transaction": [
                    {
                        "action": "insert",
                        "collection": "parcels",
                        "feature": _sample_feature(
                            coll,
                            fid=uuid4(),
                            geometry=_malformed_geometry(coll),
                            properties={"label": "bad-geometry", "area_m2": 80.0},
                        ),
                    }
                ],
            },
        )

        _assert_report_shell(report, committed=False, item_count=1)
        _assert_rejected_item(
            report["items"][0],
            {
                "index": 0,
                "action": "insert",
                "collection": "parcels",
                "id": report["items"][0]["id"],
                "sqlstate": "XX000",
            },
        )
        assert _item(cur, "cadastre", "parcels", witness_id) is not None


def test_transaction_failure_leaves_connection_usable_for_next_success(
    datasets, conn_non_autocommit
):
    coll = _collection(datasets, "cadastre", "parcels")
    good_id = uuid4()

    with conn_non_autocommit.cursor() as cur:
        failed = _transaction(
            cur,
            "cadastre",
            {
                "semantic": "atomic",
                "transaction": [
                    {
                        "action": "insert",
                        "collection": "parcels",
                        "feature": _sample_feature(
                            coll,
                            fid=uuid4(),
                            geometry=_malformed_geometry(coll),
                            properties={"label": "bad-geometry", "area_m2": 90.0},
                        ),
                    }
                ],
            },
        )
        _assert_report_shell(failed, committed=False, item_count=1)
        _assert_rejected_item(
            failed["items"][0],
            {
                "index": 0,
                "action": "insert",
                "collection": "parcels",
                "id": failed["items"][0]["id"],
                "sqlstate": "XX000",
            },
        )

        succeeded = _transaction(
            cur,
            "cadastre",
            {
                "semantic": "atomic",
                "transaction": [
                    {
                        "action": "insert",
                        "collection": "parcels",
                        "feature": _sample_feature(
                            coll,
                            fid=good_id,
                            properties={
                                "label": "good-after-failure",
                                "area_m2": 100.0,
                            },
                        ),
                    }
                ],
            },
        )

        _assert_report_shell(succeeded, committed=True, item_count=1)
        _assert_committed_item(
            succeeded["items"][0],
            {
                "index": 0,
                "action": "insert",
                "collection": "parcels",
                "id": good_id,
                "status": "created",
            },
        )
        assert _item(cur, "cadastre", "parcels", good_id) is not None


def test_transaction_items_see_earlier_document_effects_before_commit(datasets, conn):
    coll = _collection(datasets, "cadastre", "parcels")
    shared_id = uuid4()

    with conn.cursor() as cur:
        report = _transaction(
            cur,
            "cadastre",
            {
                "semantic": "atomic",
                "transaction": [
                    {
                        "action": "insert",
                        "collection": "parcels",
                        "feature": _sample_feature(
                            coll,
                            fid=shared_id,
                            properties={"label": "before-patch", "area_m2": 110.0},
                        ),
                    },
                    {
                        "action": "update",
                        "collection": "parcels",
                        "id": str(shared_id),
                        "feature": {"properties": {"label": "after-patch"}},
                    },
                ],
            },
        )

        _assert_report_shell(report, committed=True, item_count=2)
        _assert_committed_item(
            report["items"][0],
            {
                "index": 0,
                "action": "insert",
                "collection": "parcels",
                "id": shared_id,
                "status": "created",
            },
        )
        _assert_committed_item(
            report["items"][1],
            {
                "index": 1,
                "action": "update",
                "collection": "parcels",
                "id": shared_id,
                "status": "updated",
            },
        )
        got = _item(cur, "cadastre", "parcels", shared_id)
        assert got is not None
        assert got["properties"]["label"] == "after-patch"
        _remove_feature(cur, "cadastre", coll, shared_id)


def test_transaction_empty_document_commits_with_empty_items_and_no_state_change(
    datasets, conn
):
    coll = _collection(datasets, "cadastre", "parcels")

    with conn.cursor() as cur:
        witness_id = _create(
            cur,
            "cadastre",
            "parcels",
            _sample_feature(coll, properties={"label": "witness", "area_m2": 120.0}),
        )
        before = _item(cur, "cadastre", "parcels", witness_id)

        report = _transaction(
            cur, "cadastre", {"semantic": "atomic", "transaction": []}
        )

        _assert_report_shell(report, committed=True, item_count=0)
        assert report["items"] == []
        assert _item(cur, "cadastre", "parcels", witness_id) == before
        _remove_feature(cur, "cadastre", coll, witness_id)


def test_transaction_reachability_insert_works_for_every_collection(datasets, conn):
    with conn.cursor() as cur:
        for dataset in datasets:
            for coll in dataset.collections:
                fid = uuid4()
                report = _transaction(
                    cur,
                    dataset.name,
                    {
                        "semantic": "atomic",
                        "transaction": [
                            {
                                "action": "insert",
                                "collection": coll.name,
                                "feature": _sample_feature(coll, fid=fid),
                            }
                        ],
                    },
                )

                _assert_report_shell(report, committed=True, item_count=1)
                _assert_committed_item(
                    report["items"][0],
                    {
                        "index": 0,
                        "action": "insert",
                        "collection": coll.name,
                        "id": fid,
                        "status": "created",
                    },
                )
                got = _item(cur, dataset.name, coll.name, fid)
                assert got is not None
                assert str(got["id"]) == str(fid)
                _remove_feature(cur, dataset.name, coll, fid)


def test_transaction_topology_insert_succeeds_while_feature_create_is_refused(
    datasets, conn
):
    coll = _collection(datasets, "cadastre", "blocks")
    fid = uuid4()

    with conn.cursor() as cur:
        report = _transaction(
            cur,
            "cadastre",
            {
                "semantic": "atomic",
                "transaction": [
                    {
                        "action": "insert",
                        "collection": "blocks",
                        "feature": _sample_feature(
                            coll,
                            fid=fid,
                            properties={"code": "B-1"},
                        ),
                    }
                ],
            },
        )

        _assert_report_shell(report, committed=True, item_count=1)
        _assert_committed_item(
            report["items"][0],
            {
                "index": 0,
                "action": "insert",
                "collection": "blocks",
                "id": fid,
                "status": "created",
            },
        )
        assert _item(cur, "cadastre", "blocks", fid) is not None
        _remove_feature(cur, "cadastre", coll, fid)

        try:
            _create(
                cur,
                "cadastre",
                "blocks",
                _sample_feature(coll, properties={"code": "B-2"}),
            )
        except psycopg.Error:
            pass
        else:
            raise AssertionError(
                "ogc.feature_create unexpectedly accepted a topology collection"
            )


def test_transaction_data_rejection_reports_sqlstate_expected(datasets, conn):
    coll = _collection(datasets, "cadastre", "parcels")
    bad_id = uuid4()

    with conn.cursor() as cur:
        report = _transaction(
            cur,
            "cadastre",
            {
                "semantic": "atomic",
                "transaction": [
                    {
                        "action": "insert",
                        "collection": "parcels",
                        "feature": _sample_feature(
                            coll,
                            fid=bad_id,
                            geometry=_malformed_geometry(coll),
                            properties={"label": "bad-geometry", "area_m2": 130.0},
                        ),
                    }
                ],
            },
        )

        _assert_report_shell(report, committed=False, item_count=1)
        _assert_rejected_item(
            report["items"][0],
            {
                "index": 0,
                "action": "insert",
                "collection": "parcels",
                "id": bad_id,
                "sqlstate": "XX000",
            },
        )


def test_transaction_unknown_action_keeps_null_id_key_on_rejected_item(datasets, conn):
    _collection(datasets, "cadastre", "parcels")

    with conn.cursor() as cur:
        report = _transaction(
            cur,
            "cadastre",
            {
                "semantic": "atomic",
                "transaction": [{"action": "bogus", "collection": "parcels"}],
            },
        )

        _assert_report_shell(report, committed=False, item_count=1)
        _assert_rejected_item(
            report["items"][0],
            {
                "index": 0,
                "action": "bogus",
                "collection": "parcels",
                "id": None,
                "sqlstate": "P0001",
            },
        )
        assert "id" in report["items"][0]
        assert report["items"][0]["id"] is None


def test_transaction_missing_action_after_success_reports_only_rejected_item(
    datasets, conn
):
    coll = _collection(datasets, "cadastre", "parcels")
    inserted_id = uuid4()

    with conn.cursor() as cur:
        report = _transaction(
            cur,
            "cadastre",
            {
                "semantic": "atomic",
                "transaction": [
                    {
                        "action": "insert",
                        "collection": "parcels",
                        "feature": _sample_feature(
                            coll,
                            fid=inserted_id,
                            properties={"label": "will-rollback", "area_m2": 140.0},
                        ),
                    },
                    {"collection": "parcels"},
                ],
            },
        )

        _assert_report_shell(report, committed=False, item_count=1)
        _assert_rejected_item(
            report["items"][0],
            {
                "index": 1,
                "action": None,
                "collection": "parcels",
                "id": None,
                "sqlstate": "P0001",
            },
        )
        assert _item(cur, "cadastre", "parcels", inserted_id) is None


def test_transaction_missing_semantic_returns_document_level_reason(conn):
    with conn.cursor() as cur:
        report = _transaction(cur, "cadastre", {"transaction": []})

        assert set(report) == {
            "committed",
            "phase",
            "reason",
            "items",
            "structure",
            "geometry",
        }
        assert report["committed"] is False
        assert report["phase"] == "items"
        assert report["items"] == []
        assert report["structure"] == []
        assert report["geometry"] == []
        assert isinstance(report["reason"], str)
        assert report["reason"]


def test_transaction_wrong_semantic_returns_document_level_reason(conn):
    with conn.cursor() as cur:
        report = _transaction(cur, "cadastre", {"semantic": "batch", "transaction": []})

        assert report["committed"] is False
        assert report["items"] == []
        assert isinstance(report["reason"], str)
        assert report["reason"]


def test_transaction_non_array_transaction_returns_document_level_reason(conn):
    with conn.cursor() as cur:
        report = _transaction(
            cur, "cadastre", {"semantic": "atomic", "transaction": {}}
        )

        assert report["committed"] is False
        assert report["items"] == []
        assert isinstance(report["reason"], str)
        assert report["reason"]
