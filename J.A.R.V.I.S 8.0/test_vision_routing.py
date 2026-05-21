import os
import sys
from unittest.mock import MagicMock

# Ensure jarvis 8.0 directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.orchestrator import Orchestrator

def test_routing():
    print("Testing Vision Routing...")
    router = MagicMock()
    memory = MagicMock()
    researcher = MagicMock()
    executor = MagicMock()
    vision = MagicMock()
    
    # Initialize Orchestrator
    jarvis = Orchestrator(router, memory, researcher, executor, vision=vision)
    
    # Test cases
    test_queries = [
        "analyse the room",
        "what do you see in the camera?",
        "look at me",
        "analyse my screen",
        "who is in the environment?"
    ]
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        state = {"query": query, "route": "OLLAMA"}
        dispatch = jarvis._dispatch_after_routing(state)
        print(f"Dispatched to: {dispatch}")
        
        if dispatch == "vision":
            # Simulate vision_node call
            vision_state = {"query": query}
            jarvis.vision_node(vision_state)
            # Check what was passed to vision.analyze
            args, kwargs = vision.analyze.call_args
            print(f"Vision analyze called with: source='{args[0]}', prompt='{args[1]}'")
        else:
            print("FAILED: Query not routed to vision.")

if __name__ == "__main__":
    test_routing()
