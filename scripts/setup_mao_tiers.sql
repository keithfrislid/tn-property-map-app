-- setup_mao_tiers.sql
-- Run this once in the Supabase SQL Editor before running populate_mao_tiers.py

CREATE TABLE IF NOT EXISTS mao_tiers (
    id       SERIAL PRIMARY KEY,
    county   TEXT NOT NULL UNIQUE,
    tier     TEXT NOT NULL,
    mao_min  NUMERIC NOT NULL,
    mao_max  NUMERIC NOT NULL
);
