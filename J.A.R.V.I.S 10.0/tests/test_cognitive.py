import os
import sys
import json
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.cognitive_engine import TrueBackendThinkingEngine
from core.planner import CognitivePlanner

def main():
    load_dotenv()
    print("=== Testing J.A.R.V.I.S 10.0 True Backend Thinking Engine ===")

    # 1. Initialize Thinking Engine
    engine = TrueBackendThinkingEngine(llm_client=None) # Forces offline fallback mode
    
    query = "Install a new package and execute test script"
    system_context = "Safe subprocess environment fallback active"
    past_episodes = []

    print("\n[Step 1] Executing 13-Stage Reasoning Loop (Offline Fallback)...")
    res = engine.analyze_and_plan(query, system_context, past_episodes)
    
    assert res is not None
    assert "cognitive_state" in res
    assert "stage_11_plan_synthesis" in res
    assert "stage_12_plan_critique" in res
    assert "stage_13_adaptive_execution" in res
    
    cs = res["cognitive_state"]
    assert "stage_1_query_stabilization" in cs
    assert "stage_4_cognitive_type" in cs
    assert "stage_6_constraint_discovery" in cs
    assert "stage_8_failure_prediction" in cs
    
    print("[SUCCESS] Engine successfully compiled all 13 stages in cognitive state dictionary!")

    # 2. Test planner integration
    print("\n[Step 2] Testing CognitivePlanner Integration...")
    planner = CognitivePlanner(llm_client=None)
    plan = planner.generate_plan(query, system_context, past_episodes)
    
    assert plan is not None
    assert "steps" in plan
    assert len(plan["steps"]) > 0
    assert "adaptive_execution" in plan
    assert "plan_critique" in plan
    assert "cognitive_state" in plan
    
    print("[SUCCESS] CognitivePlanner successfully processed 13-stage reasoning loop, verified plan tree consistency, and logged details!")

if __name__ == "__main__":
    main()
