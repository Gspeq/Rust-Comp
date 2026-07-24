import { describe, expect, it } from "vitest";
import { isolatedMembers, operationsReducer, type OperationsState } from "./domain";
const state: OperationsState = { connection: "offline", activePanel: "Operations", objectives: [], members: [] };
describe("operations state", () => {
  it("switches panels without discarding live state", () => { expect(operationsReducer(state, { type: "panel", value: "Friends" }).activePanel).toBe("Friends"); });
  it("flags only online separated teammates", () => { expect(isolatedMembers([{id:"1",name:"A",online:true,alive:true,distanceFromLeader:500},{id:"2",name:"B",online:false,alive:true,distanceFromLeader:999}])).toHaveLength(1); });
});
