from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import boto3
import json
import os
import uuid
from datetime import datetime
from PIL import Image
from io import BytesIO
import base64
import requests

app = FastAPI(title="ArtGuard API", version="1.0.0")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to ArtGuard API",
        "version": "1.0.0",
        "endpoints": {
            "/health": "Health check",
        }
    }
