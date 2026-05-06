import json
import os

MEMORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory.json")


class Memory:
    def __init__(self):
        self.features = []
        self.load()

    def load(self):
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                self.features = json.load(f)

    def save(self):
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.features, f, indent=4)

    def add_features(self, new_features: list):
        """Adds features if they don't already exist"""
        existing_names = {f["feature_name"].lower() for f in self.features}
        added = 0
        for f in new_features:
            if f["feature_name"].lower() not in existing_names:
                self.features.append(f)
                added += 1
        if added > 0:
            self.save()
        return added

    def get_all_features(self):
        return self.features
