"""
Unit tests for Phase 11 Decision Audit Trail in Recommendation Engine.
"""
import pytest
from src.recommendation_engine import (
    update_manager_action,
    get_saved_recommendations,
    ALLOWED_MANAGER_ACTIONS
)
from src.database import get_connection

def test_update_manager_action():
    # Setup a dummy recommendation
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO recommendations (
            timestamp, store_id, product_id, issue_type, priority_score,
            evidence, recommendation, confidence, manager_action
        ) VALUES ('2023-12-31T00:00:00', 1, 1, 'stockout_risk', 85.0, '{}', 'Test Rec', 'High', 'Review')
    """)
    rec_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Valid Review
    assert update_manager_action(rec_id, "Review", "needs checking")
    
    # Valid Accept
    assert update_manager_action(rec_id, "Accept")
    
    # Valid Dismiss
    assert update_manager_action(rec_id, "Dismiss", "not needed")
    
    # Invalid action
    with pytest.raises(ValueError, match="Invalid action"):
        update_manager_action(rec_id, "UnknownAction")
        
    # Unknown rec_id
    with pytest.raises(ValueError, match="Unknown recommendation_id"):
        update_manager_action(99999, "Accept")
        
    # Check that recommendation text and evidence are preserved
    saved = get_saved_recommendations()
    found = next((r for r in saved if r["recommendation_id"] == rec_id), None)
    assert found is not None
    assert found["recommendation"] == 'Test Rec'
    assert found["manager_action"] == 'Dismiss'
    assert found["action_note"] == 'not needed'
    assert found["action_timestamp"] is not None
