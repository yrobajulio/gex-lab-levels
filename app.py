from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
sys.path.append(os.path.dirname(__file__))
from scripts.calcular_niveles import calcular_niveles

app = FastAPI(title="GEX Lab Levels API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "GEX Lab Levels API running"}

@app.get("/levels/{ticker}")
def get_levels(ticker: str):
    resultado = calcular_niveles(ticker.upper())
    if not resultado:
        return {"error": f"{ticker.upper()} not found or no options available"}
    return resultado
