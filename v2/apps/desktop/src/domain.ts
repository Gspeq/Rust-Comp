export type ConnectionState = "offline" | "connecting" | "online";
export type ObjectiveStatus = "open" | "claimed" | "in_progress" | "completed" | "cancelled";
export interface Objective { id: string; title: string; grid?: string; status: ObjectiveStatus; priority: number; assignedTo?: string; }
export interface TeamMember { id: string; name: string; online: boolean; alive: boolean; grid?: string; distanceFromLeader?: number; }
export interface Provider { id: string; display_name: string; category: string; free_to_use: boolean; requires_account: boolean; capabilities: string[]; privacy_note: string; }
export interface OperationsState { connection: ConnectionState; members: TeamMember[]; objectives: Objective[]; activePanel: string; }
export type OperationsAction = { type: "connection"; value: ConnectionState } | { type: "panel"; value: string } | { type: "objectives"; value: Objective[] };
export function operationsReducer(state: OperationsState, action: OperationsAction): OperationsState {
  switch (action.type) {
    case "connection": return { ...state, connection: action.value };
    case "panel": return { ...state, activePanel: action.value };
    case "objectives": return { ...state, objectives: action.value };
  }
}
export function isolatedMembers(members: TeamMember[], threshold = 300): TeamMember[] {
  return members.filter((member) => member.online && (member.distanceFromLeader ?? 0) > threshold);
}
