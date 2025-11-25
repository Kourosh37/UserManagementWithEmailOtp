from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine
from app import models
from app import auth

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Auth Service", version="1.0.0")

# Allow local frontend (e.g., Live Server on :5500) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["authentication"])

@app.get("/")
def read_root():
    return {"message": "Auth Service is running!"}
