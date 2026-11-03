from modules.experiment_engine.engine import ExperimentEngine, ProtocolDefinition


def test_engine_detects_out_of_order_unknown_and_low_confidence():
    protocol = ProtocolDefinition("p", "1", "test", [
        {"step_id": "A", "sequence": 1}, {"step_id": "B", "sequence": 2}
    ], minimum_confidence=0.6)
    engine = ExperimentEngine(protocol)
    assert engine.validate("STEP_STARTED", "B", 0.9, [{"step_id": "A", "status": "pending"}])[1] == "out_of_order"
    assert engine.validate("STEP_STARTED", "C", 0.9, [])[1] == "unknown_step"
    assert engine.validate("STEP_STARTED", "A", 0.2, [])[1] == "low_confidence"


def test_engine_rejects_completion_without_start():
    protocol = ProtocolDefinition("p", "1", "test", [{"step_id": "A", "sequence": 1}])
    assert ExperimentEngine(protocol).validate("STEP_COMPLETED", "A", 0.9, [{"step_id": "A", "status": "pending"}])[1] == "invalid_transition"
