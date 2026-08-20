from gcjobs import db


def test_terminal_success_event_does_not_recount_processed_features() -> None:
    batch_updates = db._run_updates_for_event(
        {
            "event": "import.batch.succeeded",
            "batch_size": 100,
            "total_features": 100,
        }
    )
    completion_updates = db._run_updates_for_event(
        {
            "event": "import.completed.succeeded",
            "imported_features": 100,
            "total_features": 100,
        }
    )

    assert batch_updates["processed_features"] == 100
    assert batch_updates["succeeded_features"] == 100
    assert completion_updates["processed_features"] == 0
    assert completion_updates["succeeded_features"] == 0
    assert completion_updates["status"] == "completed"
    assert completion_updates["is_terminal"] is True
