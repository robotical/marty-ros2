# Header stamp is publication time. Ages use a monotonic host clock.
std_msgs/Header header
uint64 generation
string connection_state
bool connected
bool telemetry_fresh
bool motion_status_valid
bool moving
bool paused
int32 queued_movements
float64 telemetry_age_seconds
float64 motion_status_age_seconds
uint64 dropped_samples
string last_error
