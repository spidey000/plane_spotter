-- Migration script to add airport_icao to existing tables
-- Run this in the Supabase SQL Editor

-- 1. interesting_models
ALTER TABLE interesting_models 
ADD COLUMN IF NOT EXISTS airport_icao TEXT DEFAULT 'LEMD' NOT NULL;

-- Drop old unique constraint on just icao_code
ALTER TABLE interesting_models 
DROP CONSTRAINT IF EXISTS interesting_models_icao_code_key;

-- Add new composite unique constraint
ALTER TABLE interesting_models 
ADD CONSTRAINT interesting_models_airport_icao_code_key UNIQUE (airport_icao, icao_code);


-- 2. registrations
ALTER TABLE registrations 
ADD COLUMN IF NOT EXISTS airport_icao TEXT DEFAULT 'LEMD' NOT NULL;

ALTER TABLE registrations 
DROP CONSTRAINT IF EXISTS registrations_registration_key;

ALTER TABLE registrations 
ADD CONSTRAINT registrations_airport_registration_key UNIQUE (airport_icao, registration);


-- 3. interesting_registrations
ALTER TABLE interesting_registrations 
ADD COLUMN IF NOT EXISTS airport_icao TEXT DEFAULT 'LEMD' NOT NULL;

ALTER TABLE interesting_registrations 
DROP CONSTRAINT IF EXISTS interesting_registrations_registration_key;

ALTER TABLE interesting_registrations 
ADD CONSTRAINT interesting_registrations_airport_registration_key UNIQUE (airport_icao, registration);


-- 4. flight_history
ALTER TABLE flight_history 
ADD COLUMN IF NOT EXISTS airport_icao TEXT DEFAULT 'LEMD' NOT NULL;
