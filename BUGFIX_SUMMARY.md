# Aircraft Tracking Bug Fixes Summary

## Issues Fixed

### 1. **Database Updates Were Disabled** ✅
**Problem**: The system wasn't updating the `last_seen` and `times_seen` fields for known aircraft.
**Solution**: Re-enabled the database update call in `utils/data_processing.py:224`

**Before**:
```python
logger.debug(f"Won;t update record {flight['registration']} for now")
#await bm.update_record(config['baserow']['tables']['registrations'], payload, flight)
```

**After**:
```python
await bm.update_record(config['baserow']['tables']['registrations'], payload, flight)
logger.debug(f"Updated record for {flight['registration']} in table {config['baserow']['tables']['registrations']}")
```

### 2. **No Long-Term Deduplication Logic** ✅
**Problem**: Aircraft were being posted every time they appeared, even if they were regular visitors.
**Solution**: Added 6-month cooldown system based on `last_seen` timestamp.

**Changes**:
- Added `posting_cooldown_hours` configuration (default: 4320 hours = 6 months)
- Added `seen_recently` flag to track if aircraft was seen within cooldown period
- Added logic to post aircraft only if they haven't been seen in 6+ months
- Interesting registrations are always posted regardless of cooldown

### 3. **Missing Long-Term Tracking Logic** ✅
**Problem**: No way to distinguish between regular visitors and aircraft returning after long absences.
**Solution**: Added logic to treat aircraft as interesting if not seen in 6+ months.

**Implementation**:
- Check database for `last_seen` timestamp
- Compare with current time and 6-month cooldown period
- Post aircraft that return after 6+ months as "RETURNED_AFTER_6_MONTHS"

### 4. **Incorrect Database Access in Interesting Registrations** ✅
**Problem**: The system was incorrectly accessing the interesting registrations database, causing previously seen aircraft to be flagged as new.
**Solution**: Fixed database access pattern to correctly retrieve registration-specific data.

**Before**:
```python
reason = interesting_reg_db['registration']['reason']  # Incorrect
```

**After**:
```python
reason = interesting_reg_db[flight['registration']].get('reason', None)  # Correct
```

## Code Changes Made

### Files Modified:
1. **`utils/data_processing.py`**:
   - Re-enabled database updates (line 224)
   - Added 6-month cooldown checking logic using `last_seen` (lines 189-232)
   - Added `seen_recently` return value (line 305)
   - **FIXED**: Corrected database access pattern for interesting registrations (line 208)
   - **FIXED**: Improved logic for retrieving reason field from appropriate database (lines 235-240)

2. **`main.py`**:
   - Updated function call to handle `seen_recently` return value (line 224)
   - Added posting decision logic based on 6-month cooldown (lines 238-245)
   - Added "RETURNED_AFTER_6_MONTHS" reason tracking (line 234)

3. **`config/config.json`**:
   - Added `posting_cooldown_hours: 4320` (6 months) to flight configuration

4. **Documentation**:
   - Created `AIRCRAFT_TRACKING.md` - Complete system behavior documentation
   - Updated behavior descriptions to reflect cooldown system

## New Behavior

### Regular Aircraft:
1. ✅ **First detection** → Posted as "FIRST_SEEN"
2. ✅ **Subsequent detections (within 6 months)** → Tracked in database, NOT posted
3. ✅ **Detection after 6+ months** → Posted as "RETURNED_AFTER_6_MONTHS"

### Interesting Registrations:
1. ✅ Always posted, regardless of when last seen
2. ✅ Useful for tracking VIP aircraft, special planes, etc.

### Database Tracking:
1. ✅ `times_seen` counter properly increments on every sighting
2. ✅ `last_seen` timestamp updated on every detection
3. ✅ Historical data preserved for long-term analysis

## Configuration

The new `posting_cooldown_hours` setting controls how long to wait before posting the same aircraft again:
- **4320** (default): Post same aircraft only if not seen in 6 months
- **2160**: Post same aircraft if not seen in 3 months  
- **720**: Post same aircraft if not seen in 1 month
- **0**: Disable cooldown (post every time - not recommended)

## Testing Recommendations

To verify the fixes work:

1. **Test Database Updates**: Check that `times_seen` increments when same aircraft appears multiple times
2. **Test Cooldown Logic**: Verify aircraft isn't posted twice within the cooldown period
3. **Test Interesting Override**: Verify interesting registrations are always posted
4. **Test First Seen**: Verify new aircraft are properly marked as first seen and posted
5. **Test Previously Seen Aircraft**: Verify that previously seen aircraft are correctly identified and not flagged as new

## Configuration Example

```json
{
  "flight": {
    "time_range_hours": 2,
    "posting_cooldown_hours": 4320,
    "preview_data": false
  }
}
```

## Impact

- ✅ **Eliminates spam posts** of regular aircraft while highlighting returning visitors
- ✅ **Preserves all tracking data** with proper database updates
- ✅ **Maintains interesting aircraft notifications** for manually curated planes
- ✅ **Highlights aircraft that return after long absences** (6+ months)
- ✅ **Configurable cooldown period** for different tracking needs
- ✅ **Better logging** for debugging posting decisions
- ✅ **Long-term historical tracking** for spotting patterns
- ✅ **Fixed critical bug** that was causing previously seen aircraft to be flagged as new