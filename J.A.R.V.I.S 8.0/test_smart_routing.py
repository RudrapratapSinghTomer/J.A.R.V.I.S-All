import os
import sys
from unittest.mock import MagicMock

# Ensure jarvis 8.0 directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.orchestrator import Orchestrator

def test_smart_routing():
    print("Testing Smart Semantic Routing...")
    router = MagicMock()
    memory = MagicMock()
    researcher = MagicMock()
    executor = MagicMock()
    vision = MagicMock()
    
    # Initialize Orchestrator
    jarvis = Orchestrator(router, memory, researcher, executor, vision=vision)
    
    # Test cases
    test_data = [
        {"query": "analyse the room", "intent": "VISION"},
        {"query": "tell me what's happening around me", "intent": "VISION"},
        {"query": "write a python script", "intent": "CODE"},
        {"query": "who are you?", "intent": "GENERAL"}
    ]
    
    for item in test_data:
        query = item["query"]
        intent = item["intent"]
        print(f"\nQuery: '{query}' (Intent: {intent})")
        
        # Mock router.route
        router.route.return_value = {"provider": "OLLAMA", "intent": intent}
        
        # Test routing node
        routing_result = jarvis.routing_node({"query": query})
        print(f"Routing Node Result: {routing_result}")
        
        # Test dispatch
        state = {"query": query, "route": routing_result["route"], "intent": routing_result["intent"]}
        dispatch = jarvis._dispatch_after_routing(state)
        print(f"Dispatched to: {dispatch}")
        
        if intent == "VISION" and dispatch == "vision":
             print("SUCCESS: Correctly routed to vision.")
        elif intent == "CODE" and dispatch == "specialist":
             print("SUCCESS: Correctly routed to specialist.")
        elif intent == "GENERAL" and dispatch == "OLLAMA":
             print("SUCCESS: Correctly routed to local SLM.")
        else:
             print(f"FAILED: Unexpected dispatch to {dispatch}")

if __name__ == "__main__":
    test_smart_routing()
