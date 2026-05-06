# Import necessary libraries and models
import os
from transformers import pipeline


# Define the function to generate the system summary
def generate_system_summary():
    # Load the model
    model_name = "meta/llama-3.1-70b-instruct"
    model = pipeline("text-generation", model=model_name)

    # Define the prompt
    prompt = "Generate a system summary for J.A.R.V.I.S 3.0"

    # Generate the system summary
    summary = model(prompt, max_length=200)

    # Write the summary to a file
    with open("system_summary.txt", "w") as f:
        f.write(summary[0]["generated_text"])


# Call the function
generate_system_summary()
