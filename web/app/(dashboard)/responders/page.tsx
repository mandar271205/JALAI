"use client";
// Route: /responders — Field Operations & Tactical Task Management
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users, UserCheck, Clock, MapPin, Plus, CheckCircle, Navigation,
  AlertTriangle, Filter, Shield, Activity,
} from "lucide-react";
import { toast } from "sonner";
import { respondersApi } from "@/lib/api/responders";
import {
  PageHeader, StatusBadge, PriorityBadge, EmptyState, LoadingSkeleton,
  ErrorState, Timestamp, KpiCard,
} from "@/components/common";
import { useAuthStore } from "@/store";
import type { ResponderTask } from "@/types";

const STATUS_FILTERS = ["", "ASSIGNED", "EN_ROUTE", "ON_SITE", "RESOLVED", "CANCELLED"];

export default function RespondersPage() {
  const { canDoAction } = useAuthStore();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [showNewTaskModal, setShowNewTaskModal] = useState(false);

  // New task form state
  const [newTask, setNewTask] = useState({
    incident_id: "INC-DEMO-01",
    responder_id: "RESP-001",
    task_type: "WATER_LEVEL_VERIFICATION",
    priority: "P1_CRITICAL",
    instructions: "Deploy mobile sensor and establish perimeter cordon at downstream culvert.",
    latitude: 19.076,
    longitude: 72.8777,
  });

  const { data: tasks, isLoading, isError, refetch } = useQuery({
    queryKey: ["responder-tasks", statusFilter],
    queryFn: () => respondersApi.listTasks({ status: statusFilter || undefined }),
    refetchInterval: 15_000,
  });

  const createTaskMutation = useMutation({
    mutationFn: () => respondersApi.createTask(newTask),
    onSuccess: () => {
      toast.success("Tactical task dispatched to field responder");
      setShowNewTaskModal(false);
      queryClient.invalidateQueries({ queryKey: ["responder-tasks"] });
    },
    onError: (err: Error) => {
      toast.error("Failed to dispatch task", { description: err.message });
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({
      taskId,
      action,
      baseVersion,
    }: {
      taskId: string;
      action: string;
      baseVersion: number;
    }) => respondersApi.applyAction(taskId, { action, base_version: baseVersion }),
    onSuccess: (_, { action }) => {
      toast.success(`Task status updated: ${action}`);
      queryClient.invalidateQueries({ queryKey: ["responder-tasks"] });
    },
    onError: (err: Error) => {
      toast.error("Task transition failed", { description: err.message });
    },
  });

  // Calculate quick metrics
  const totalTasks = tasks?.length || 0;
  const activeTasks = tasks?.filter((t) => ["ASSIGNED", "EN_ROUTE", "ON_SITE"].includes(t.status)).length || 0;
  const onSiteCount = tasks?.filter((t) => t.status === "ON_SITE").length || 0;
  const resolvedCount = tasks?.filter((t) => t.status === "RESOLVED").length || 0;

  return (
    <div>
      <PageHeader
        title="Field Responders & Dispatch"
        description="Real-time incident response teams, task allocation, and field sensor telemetry"
        actions={
          canDoAction("create_incident") && (
            <button
              onClick={() => setShowNewTaskModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> Dispatch Task
            </button>
          )
        }
      />

      <div className="page-content space-y-6">
        {/* KPI Summary Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard
            title="Total Assigned"
            value={totalTasks}
            icon={<Users className="w-4 h-4 text-blue-600" />}
          />
          <KpiCard
            title="Active Operations"
            value={activeTasks}
            icon={<Activity className="w-4 h-4 text-amber-600" />}
          />
          <KpiCard
            title="Units On Site"
            value={onSiteCount}
            icon={<Navigation className="w-4 h-4 text-purple-600" />}
          />
          <KpiCard
            title="Tasks Resolved"
            value={resolvedCount}
            icon={<CheckCircle className="w-4 h-4 text-emerald-600" />}
          />
        </div>

        {/* Status Filter Bar */}
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-gray-400" />
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                statusFilter === s
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {s || "All Tasks"}
            </button>
          ))}
        </div>

        {/* Task List Table */}
        <div className="jr-card">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(4)].map((_, i) => (
                <LoadingSkeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : isError ? (
            <ErrorState message="Could not retrieve responder tasks" onRetry={refetch} />
          ) : !tasks?.length ? (
            <EmptyState
              title="No Tasks Found"
              message="No responder tasks match the specified filter."
              icon={<Users className="w-6 h-6 text-gray-400" />}
            />
          ) : (
            <div className="divide-y divide-gray-50">
              {tasks.map((task: ResponderTask) => (
                <div key={task.task_id} className="p-4 hover:bg-gray-50/50 transition-colors">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div className="space-y-1.5 flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <StatusBadge status={task.status} />
                        <PriorityBadge priority={task.priority} />
                        <span className="text-xs font-mono text-gray-400">ID: {task.task_id}</span>
                        <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded font-mono">
                          Responder: {task.responder_id}
                        </span>
                      </div>

                      <p className="text-sm font-semibold text-gray-900">{task.instructions}</p>

                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <span className="flex items-center gap-1 font-mono">
                          <MapPin className="w-3.5 h-3.5 text-blue-500" />
                          {(task.latitude ?? 19.076).toFixed(4)}, {(task.longitude ?? 72.8777).toFixed(4)}
                        </span>
                        <span>Incident: {task.incident_id}</span>
                        {task.measured_depth_cm !== null && task.measured_depth_cm !== undefined && (
                          <span className="text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded">
                            Field Sensor Depth: {task.measured_depth_cm} cm
                          </span>
                        )}
                        <Timestamp iso={task.updated_at || task.assigned_at} relative />
                      </div>
                    </div>

                    {/* Quick State Transitions */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {task.status === "ASSIGNED" && (
                        <button
                          onClick={() =>
                            actionMutation.mutate({
                              taskId: task.task_id,
                              action: "START_TRAVEL",
                              baseVersion: task.version || 1,
                            })
                          }
                          disabled={actionMutation.isPending}
                          className="px-2.5 py-1.5 text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg font-medium transition-colors"
                        >
                          Start Travel
                        </button>
                      )}

                      {task.status === "EN_ROUTE" && (
                        <button
                          onClick={() =>
                            actionMutation.mutate({
                              taskId: task.task_id,
                              action: "ARRIVE",
                              baseVersion: task.version || 1,
                            })
                          }
                          disabled={actionMutation.isPending}
                          className="px-2.5 py-1.5 text-xs bg-purple-50 text-purple-700 hover:bg-purple-100 rounded-lg font-medium transition-colors"
                        >
                          Mark Arrived
                        </button>
                      )}

                      {task.status === "ON_SITE" && (
                        <button
                          onClick={() =>
                            actionMutation.mutate({
                              taskId: task.task_id,
                              action: "RESOLVE",
                              baseVersion: task.version || 1,
                            })
                          }
                          disabled={actionMutation.isPending}
                          className="px-2.5 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-medium transition-colors"
                        >
                          Resolve Task
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Modal: Dispatch Task */}
        {showNewTaskModal && (
          <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-xl space-y-4">
              <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
                <Users className="w-5 h-5 text-blue-600" />
                Dispatch Field Tactical Unit
              </h3>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Responder Unit ID *
                  </label>
                  <input
                    type="text"
                    value={newTask.responder_id}
                    onChange={(e) => setNewTask({ ...newTask, responder_id: e.target.value })}
                    className="w-full text-xs p-2.5 border border-gray-200 rounded-lg"
                    required
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      Incident Link *
                    </label>
                    <input
                      type="text"
                      value={newTask.incident_id}
                      onChange={(e) => setNewTask({ ...newTask, incident_id: e.target.value })}
                      className="w-full text-xs p-2.5 border border-gray-200 rounded-lg"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">Priority</label>
                    <select
                      value={newTask.priority}
                      onChange={(e) => setNewTask({ ...newTask, priority: e.target.value })}
                      className="w-full text-xs p-2.5 border border-gray-200 rounded-lg bg-white"
                    >
                      <option value="P1_CRITICAL">P1 Critical</option>
                      <option value="P2_HIGH">P2 High</option>
                      <option value="P3_MEDIUM">P3 Medium</option>
                      <option value="P4_LOW">P4 Low</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">Latitude</label>
                    <input
                      type="number"
                      step="0.0001"
                      value={newTask.latitude}
                      onChange={(e) => setNewTask({ ...newTask, latitude: parseFloat(e.target.value) })}
                      className="w-full text-xs p-2.5 border border-gray-200 rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">Longitude</label>
                    <input
                      type="number"
                      step="0.0001"
                      value={newTask.longitude}
                      onChange={(e) => setNewTask({ ...newTask, longitude: parseFloat(e.target.value) })}
                      className="w-full text-xs p-2.5 border border-gray-200 rounded-lg"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Operational Instructions *
                  </label>
                  <textarea
                    value={newTask.instructions}
                    onChange={(e) => setNewTask({ ...newTask, instructions: e.target.value })}
                    rows={3}
                    className="w-full text-xs p-2.5 border border-gray-200 rounded-lg"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setShowNewTaskModal(false)}
                  className="px-4 py-2 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => createTaskMutation.mutate()}
                  disabled={createTaskMutation.isPending}
                  className="px-4 py-2 text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 rounded-lg shadow-sm"
                >
                  {createTaskMutation.isPending ? "Dispatching..." : "Confirm Dispatch"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
