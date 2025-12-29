from fastapi import FastAPI

app = FastAPI(title="TASK MANAGEMENT API")

# Rooting


@app.get("/")
def read_root() -> dict:
    return {"message": "Task Management API", "status": "Running"}
