from src.qwen_runner import run_qwen_model
from src.prover9_runner import run_prover9


def run_experiment(input_data: str):
    # Run Qwen model on input_data
    qwen_output = run_qwen_model(input_data)
    
    # Run Prover9 on input_data
    prover9_output = run_prover9(input_data)

    # Placeholder for experiment evaluation or result processing
    print("Qwen output:", qwen_output)
    print("Prover9 output:", prover9_output)


if __name__ == '__main__':
    sample_input = "Example problem statement"
    run_experiment(sample_input)
