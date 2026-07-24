CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  steam_id TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  avatar_url TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  public_key TEXT NOT NULL,
  last_seen_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS friendships (
  id TEXT PRIMARY KEY,
  requester_id TEXT NOT NULL,
  addressee_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','accepted','declined','blocked')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(requester_id, addressee_id)
);
CREATE TABLE IF NOT EXISTS blocked_users (
  blocker_id TEXT NOT NULL,
  blocked_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(blocker_id, blocked_id)
);
CREATE TABLE IF NOT EXISTS teams (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS team_memberships (
  team_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  joined_at TEXT NOT NULL,
  PRIMARY KEY(team_id, user_id)
);
CREATE TABLE IF NOT EXISTS server_profiles (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  game_endpoint TEXT NOT NULL,
  display_name TEXT NOT NULL,
  world_size INTEGER,
  map_seed INTEGER,
  wipe_at TEXT,
  public_metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS room_presence (
  team_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  coordinator INTEGER NOT NULL DEFAULT 0,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY(team_id, user_id, device_id)
);
CREATE TABLE IF NOT EXISTS objectives (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  grid TEXT,
  status TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  assigned_to TEXT,
  expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tactical_markers (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  label TEXT NOT NULL,
  x_fraction REAL NOT NULL,
  y_fraction REAL NOT NULL,
  radius_meters REAL,
  created_by TEXT NOT NULL,
  expires_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shared_notes (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  created_by TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shopping_requests (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  item_name TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  priority INTEGER NOT NULL DEFAULT 1,
  requested_by TEXT NOT NULL,
  claimed_by TEXT,
  completed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS smart_device_bindings (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  server_profile_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  device_type TEXT NOT NULL,
  minimum_role TEXT NOT NULL DEFAULT 'coordinator',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_rules (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  name TEXT NOT NULL,
  rule_type TEXT NOT NULL,
  configuration TEXT NOT NULL DEFAULT '{}',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alarm_events (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  source_id TEXT,
  severity INTEGER NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS alarm_acknowledgements (
  alarm_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  acknowledged_at TEXT NOT NULL,
  PRIMARY KEY(alarm_id, user_id)
);
CREATE TABLE IF NOT EXISTS integration_connections (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  encrypted_configuration TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_endpoints (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  encrypted_destination TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_log (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  actor_id TEXT,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_log_team_time ON event_log(team_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_objectives_team_status ON objectives(team_id, status);
CREATE INDEX IF NOT EXISTS idx_markers_team_time ON tactical_markers(team_id, created_at);
