"""Runner script to launch the JalRakshak ML Inference Microservice."""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("ML_PORT", "8001"))
    host = os.getenv("ML_HOST", "0.0.0.0")
    print(f"Starting JalRakshak ML Inference Service on {host}:{port}...")
    uvicorn.run("jalrakshak_ml.serving.app:app", host=host, port=port, log_level="info")
