-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- Aircraft Models (Global)
CREATE TABLE aircraft_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    icao_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT
);

-- Interesting Models (Per Airport)
CREATE TABLE interesting_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    airport_icao TEXT NOT NULL, -- e.g., 'LEMD', 'LEBL'
    icao_code TEXT NOT NULL, -- e.g., 'A388'
    reason TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(airport_icao, icao_code)
);

-- Registrations (Per Airport History/Knowledge Base)
-- If you want to track "first seen" per airport, this needs to be per airport.
CREATE TABLE registrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    airport_icao TEXT NOT NULL, -- e.g., 'LEMD'
    registration TEXT NOT NULL,
    aircraft_type_icao TEXT,
    airline_icao TEXT,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    image_url TEXT,
    UNIQUE(airport_icao, registration)
);

-- Interesting Registrations (Per Airport Configuration)
CREATE TABLE interesting_registrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    airport_icao TEXT NOT NULL,
    registration TEXT NOT NULL,
    reason TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(airport_icao, registration)
);

-- Flight History (Log of all processed flights to prevent duplicates)
CREATE TABLE flight_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    airport_icao TEXT NOT NULL,
    flight_id_external TEXT NOT NULL, -- Unique ID from provider
    registration TEXT,
    flight_number TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_flight_history_external_id ON flight_history(flight_id_external);
CREATE INDEX idx_registrations_registration ON registrations(registration);
