# MLflow experiment tracking and run tracing for agent runs.
# TODO: implement full tracing in next prompt.


def start_run(experiment_name: str, run_name: str | None = None):
    """Placeholder: starts an MLflow run. Returns None until implemented."""
    raise NotImplementedError("mlflow_tracing not yet implemented")


def log_params(params: dict) -> None:
    """Placeholder: log parameters to the active MLflow run."""
    raise NotImplementedError("mlflow_tracing not yet implemented")


def log_metrics(metrics: dict) -> None:
    """Placeholder: log metrics to the active MLflow run."""
    raise NotImplementedError("mlflow_tracing not yet implemented")


def end_run() -> None:
    """Placeholder: end the active MLflow run."""
    raise NotImplementedError("mlflow_tracing not yet implemented")
