API Security Gateway with Hybrid Detection Engine
📌 Overview

This project implements a production-inspired API Security Gateway that protects backend APIs from abuse, unauthorized access, and anomalous behavior. The gateway sits between clients and backend services, enforcing security policies, logging telemetry, and performing real-time behavioral analysis using a hybrid rule-based + machine learning approach.

Unlike traditional dashboards, this system acts as an active enforcement layer, inspecting and controlling every request before it reaches the backend.

🎯 Motivation

Modern applications increasingly expose functionality through APIs, making APIs the primary attack surface. Common threats include:

API abuse and excessive usage

Credential stuffing and unauthorized access

Bot traffic and automated scraping

Gateway bypass attacks

Behavioral anomalies invisible to static rules

This project addresses these challenges by combining deterministic security rules with data-driven behavioral modeling, while maintaining low latency.

🏗️ High-Level Architecture
Client / Application
        ↓
API Security Gateway (Port 8000)
        ↓
Security Enforcement + Telemetry
        ↓
Protected Backend API (Port 9000)


All external traffic enters through the Gateway

The backend API is zero-trust protected

Redis provides real-time state

PostgreSQL stores persistent security telemetry

Machine learning runs asynchronously

🧱 Technology Stack

Backend & Gateway

Python

FastAPI

Uvicorn

Security & Telemetry

PostgreSQL (SQLAlchemy ORM)

Redis (sliding window state)

Machine Learning

scikit-learn (Isolation Forest)

NumPy

Other

asyncio (non-blocking execution)

UUID-based request correlation

🧩 Implemented Phases
✅ Phase 0 — System Architecture

Gateway–backend separation

Enforced request flow through gateway

Independent services for realism

✅ Phase 1 — API Key Authentication

X-API-KEY based client authentication

Proper HTTP status handling (401, 200)

Prevents unauthorized access

✅ Phase 2 — Zero-Trust Backend Lockdown

Backend accepts requests only from gateway

Internal gateway secret (X-Gateway-Token)

Eliminates direct backend access

✅ Phase 3 — Rate Limiting & Abuse Control

Sliding window rate limiter

Configurable thresholds

Prevents brute force and excessive usage

Throttled requests return 429

✅ Phase 4 — Persistent Security Telemetry (PostgreSQL)
Phase 4.1 — Database Setup

PostgreSQL integration

Centralized DB configuration

Shared schema across services

Phase 4.2 — Gateway Security Logging

Logs every request decision:

ALLOW / BLOCK / THROTTLE

Stores metadata:

client IP

API key

endpoint

HTTP method

reason

status code

timestamp

Phase 4.3 — Backend Telemetry

Backend latency measurement

Backend event logging

Correlation via X-Request-ID

Phase 4.4 — Lifecycle & Observability

FastAPI lifespan-based initialization

Automatic schema creation

End-to-end request traceability

✅ Phase 5 — Hybrid Detection Engine (Rule-Based + ML)
Phase 5.1 — DWDM Feature Engineering

Behavioral features inspired by Data Warehousing & Data Mining (DWDM):

Total requests per window

Unique endpoints accessed

Inter-arrival time variance

Requests per second

Endpoint entropy

Blocked ratio

Throttled ratio

These features describe behavior, not payload content.

Phase 5.2 — Redis Sliding Window

Redis sorted sets per API key

Time-based sliding window

Event ID correlation

Automatic expiration

Near-zero latency state tracking

Phase 5.3 — Feature Materialization & ML Preparation

Redis → PostgreSQL event materialization

Type-safe ID handling

Feature extraction from live traffic

ML model initialization and baseline fitting

🔬 Machine Learning Approach

Model: Isolation Forest (unsupervised)

Purpose: Detect anomalous API usage patterns

Execution: Asynchronous (non-blocking)

Input: DWDM behavioral feature vectors

Output: Anomaly score logged as security telemetry

The ML pipeline complements rule-based controls rather than replacing them.

🧠 Key Design Principles

Zero Trust: Backend never trusts direct requests

Defense in Depth: Auth + rate limit + behavior analysis

Observability First: Every decision is logged

Low Latency: Redis + async ML ensure fast responses

Extensibility: Designed for dashboards and future policies

🚀 Current Capabilities

Secure API gateway with enforcement

Abuse and rate-limit protection

Persistent security telemetry

Real-time behavioral modeling

ML-ready anomaly detection pipeline

Production-inspired architecture

🔜 Planned Enhancements

Hybrid rule + ML decision engine

Adaptive enforcement thresholds

Admin analytics dashboard

Dockerized deployment

Multi-instance scalability

📚 Academic Context

This project is suitable for:

Final-year undergraduate submission

Security-focused system design evaluation

Demonstrating applied DWDM and ML concepts
