import math
from typing import Any

from ortools.linear_solver import pywraplp


class ResourceOptimizationEngine:
    """
    Emergency Response Resource Recommendation Engine using Google OR-Tools.
    Optimizes multi-commodity assignment of:
    - High-capacity dewatering pumps to waterlogged locations
    - Rescue teams to high-priority incidents and high-risk zones
    - Evacuees to emergency shelters based on capacity and travel time

    CRITICAL SAFETY CONSTRAINT:
    Never auto-dispatch. All generated plans are recommendations requiring
    explicit authorized human review and cryptographic audit logging.
    """

    SEVERITY_WEIGHTS: dict[str, float] = {
        "CRITICAL": 100.0,
        "HIGH": 50.0,
        "MODERATE": 20.0,
        "LOW": 5.0,
    }

    def solve(
        self,
        pumps: list[dict[str, Any]],
        teams: list[dict[str, Any]],
        shelters: list[dict[str, Any]],
        incidents: list[dict[str, Any]],
        evacuation_demands: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Solves mixed-integer linear programming (MIP) resource allocation model.
        """
        if evacuation_demands is None:
            evacuation_demands = []

        solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            solver = pywraplp.Solver.CreateSolver("CBC")
        if not solver:
            raise RuntimeError("Failed to initialize Google OR-Tools MIP solver.")

        # --- 1. Decision Variables ---
        # Pump allocation: x_pump[p, i] in {0, 1} - whether pump p is assigned to incident i
        x_pump: dict[tuple[int, int], Any] = {}
        for p_idx, pump in enumerate(pumps):
            for i_idx, inc in enumerate(incidents):
                x_pump[(p_idx, i_idx)] = solver.BoolVar(f"x_pump_{p_idx}_{i_idx}")

        # Team allocation: x_team[t, i] in {0, 1} - whether team t is assigned to incident i
        x_team: dict[tuple[int, int], Any] = {}
        for t_idx, team in enumerate(teams):
            for i_idx, inc in enumerate(incidents):
                x_team[(t_idx, i_idx)] = solver.BoolVar(f"x_team_{t_idx}_{i_idx}")

        # Shelter allocation: x_shelter[s, d] >= 0 integer - evacuees from demand d assigned to shelter s
        x_shelter: dict[tuple[int, int], Any] = {}
        for s_idx, shelter in enumerate(shelters):
            for d_idx, demand in enumerate(evacuation_demands):
                max_people = demand.get("people_count", 0)
                x_shelter[(s_idx, d_idx)] = solver.IntVar(
                    0, max_people, f"x_shelter_{s_idx}_{d_idx}"
                )

        # --- 2. Constraints ---
        # Each pump can be assigned to at most one incident
        for p_idx in range(len(pumps)):
            solver.Add(solver.Sum([x_pump[(p_idx, i_idx)] for i_idx in range(len(incidents))]) <= 1)

        # Each team can be assigned to at most one incident
        for t_idx in range(len(teams)):
            solver.Add(solver.Sum([x_team[(t_idx, i_idx)] for i_idx in range(len(incidents))]) <= 1)

        # Incidents need at most required pumps (default 1 pump per incident)
        for i_idx, inc in enumerate(incidents):
            req_pumps = inc.get("required_pumps", 1)
            solver.Add(
                solver.Sum([x_pump[(p_idx, i_idx)] for p_idx in range(len(pumps))]) <= req_pumps
            )

        # Incidents need at most required teams (default 1 team per incident)
        for i_idx, inc in enumerate(incidents):
            req_teams = inc.get("required_teams", 1)
            solver.Add(
                solver.Sum([x_team[(t_idx, i_idx)] for t_idx in range(len(teams))]) <= req_teams
            )

        # Shelter capacity constraints: total assigned evacuees <= available capacity
        for s_idx, shelter in enumerate(shelters):
            cap = shelter.get("capacity", 500) - shelter.get("current_occupancy", 0)
            avail_cap = max(0, cap)
            if evacuation_demands:
                solver.Add(
                    solver.Sum(
                        [x_shelter[(s_idx, d_idx)] for d_idx in range(len(evacuation_demands))]
                    )
                    <= avail_cap
                )

        # Evacuation demand constraints: cannot assign more people than need evacuation
        for d_idx, demand in enumerate(evacuation_demands):
            need = demand.get("people_count", 0)
            if shelters:
                solver.Add(
                    solver.Sum([x_shelter[(s_idx, d_idx)] for s_idx in range(len(shelters))])
                    <= need
                )

        # --- 3. Objective Function ---
        # Maximize priority-weighted and zone-risk coverage, minimize travel time penalties
        objective_terms = []

        # Pump term: weight * (priority + zone_risk*20) - 0.1 * travel_time
        for p_idx, pump in enumerate(pumps):
            p_lat = pump.get("latitude", 19.0)
            p_lon = pump.get("longitude", 72.8)
            for i_idx, inc in enumerate(incidents):
                i_lat = inc.get("latitude", 19.0)
                i_lon = inc.get("longitude", 72.8)
                dist_km = math.sqrt((p_lat - i_lat) ** 2 + (p_lon - i_lon) ** 2) * 111.0
                est_travel_min = max(5.0, dist_km * 2.5)  # 2.5 min per km average flood transit

                sev = inc.get("severity", "MODERATE").upper()
                sev_weight = self.SEVERITY_WEIGHTS.get(sev, 20.0)
                zone_risk = inc.get("zone_risk_score", 0.5)

                benefit = sev_weight + (zone_risk * 30.0) - (0.05 * est_travel_min)
                objective_terms.append(benefit * x_pump[(p_idx, i_idx)])

        # Team term
        for t_idx, team in enumerate(teams):
            t_lat = team.get("latitude", 19.0)
            t_lon = team.get("longitude", 72.8)
            for i_idx, inc in enumerate(incidents):
                i_lat = inc.get("latitude", 19.0)
                i_lon = inc.get("longitude", 72.8)
                dist_km = math.sqrt((t_lat - i_lat) ** 2 + (t_lon - i_lon) ** 2) * 111.0
                est_travel_min = max(5.0, dist_km * 2.5)

                sev = inc.get("severity", "MODERATE").upper()
                sev_weight = self.SEVERITY_WEIGHTS.get(sev, 20.0)
                zone_risk = inc.get("zone_risk_score", 0.5)

                benefit = (sev_weight * 1.5) + (zone_risk * 40.0) - (0.08 * est_travel_min)
                objective_terms.append(benefit * x_team[(t_idx, i_idx)])

        # Shelter term: assign evacuees to nearest available shelter
        for s_idx, shelter in enumerate(shelters):
            s_lat = shelter.get("latitude", 19.0)
            s_lon = shelter.get("longitude", 72.8)
            for d_idx, demand in enumerate(evacuation_demands):
                d_lat = demand.get("latitude", 19.0)
                d_lon = demand.get("longitude", 72.8)
                dist_km = math.sqrt((s_lat - d_lat) ** 2 + (s_lon - d_lon) ** 2) * 111.0
                est_travel_min = max(5.0, dist_km * 2.0)
                benefit = 10.0 - (0.05 * est_travel_min)
                objective_terms.append(benefit * x_shelter[(s_idx, d_idx)])

        if objective_terms:
            solver.Maximize(solver.Sum(objective_terms))

        status = solver.Solve()

        # --- 4. Extract Solution ---
        suggested_pumps: list[dict[str, Any]] = []
        assigned_incident_pumps: set[int] = set()
        if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            for p_idx, pump in enumerate(pumps):
                for i_idx, inc in enumerate(incidents):
                    if x_pump[(p_idx, i_idx)].solution_value() > 0.5:
                        p_lat = pump.get("latitude", 19.0)
                        p_lon = pump.get("longitude", 72.8)
                        i_lat = inc.get("latitude", 19.0)
                        i_lon = inc.get("longitude", 72.8)
                        dist_km = math.sqrt((p_lat - i_lat) ** 2 + (p_lon - i_lon) ** 2) * 111.0
                        suggested_pumps.append(
                            {
                                "pump_id": pump.get("pump_id", f"PUMP-{p_idx}"),
                                "pump_name": pump.get("name", "High Capacity Dewatering Pump"),
                                "capacity_lps": pump.get("capacity_lps", 500),
                                "assigned_incident_id": inc.get("incident_id"),
                                "incident_title": inc.get("title"),
                                "incident_severity": inc.get("severity"),
                                "estimated_travel_time_min": round(max(5.0, dist_km * 2.5), 1),
                            }
                        )
                        assigned_incident_pumps.add(i_idx)

        suggested_teams: list[dict[str, Any]] = []
        assigned_incident_teams: set[int] = set()
        if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            for t_idx, team in enumerate(teams):
                for i_idx, inc in enumerate(incidents):
                    if x_team[(t_idx, i_idx)].solution_value() > 0.5:
                        t_lat = team.get("latitude", 19.0)
                        t_lon = team.get("longitude", 72.8)
                        i_lat = inc.get("latitude", 19.0)
                        i_lon = inc.get("longitude", 72.8)
                        dist_km = math.sqrt((t_lat - i_lat) ** 2 + (t_lon - i_lon) ** 2) * 111.0
                        suggested_teams.append(
                            {
                                "team_id": team.get("team_id", f"TEAM-{t_idx}"),
                                "team_name": team.get("name", "NDRF Quick Response Team"),
                                "team_size": team.get("team_size", 6),
                                "assigned_incident_id": inc.get("incident_id"),
                                "incident_title": inc.get("title"),
                                "incident_severity": inc.get("severity"),
                                "estimated_travel_time_min": round(max(5.0, dist_km * 2.5), 1),
                            }
                        )
                        assigned_incident_teams.add(i_idx)

        suggested_shelters: list[dict[str, Any]] = []
        allocated_demands: dict[int, int] = {}
        if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            for s_idx, shelter in enumerate(shelters):
                shelter_alloc = 0
                for d_idx in range(len(evacuation_demands)):
                    val = int(x_shelter[(s_idx, d_idx)].solution_value())
                    if val > 0:
                        shelter_alloc += val
                        allocated_demands[d_idx] = allocated_demands.get(d_idx, 0) + val
                if shelter_alloc > 0:
                    cap = shelter.get("capacity", 500)
                    occ = shelter.get("current_occupancy", 0)
                    suggested_shelters.append(
                        {
                            "shelter_id": shelter.get("shelter_id", f"SHELTER-{s_idx}"),
                            "shelter_name": shelter.get(
                                "name", "Municipal Emergency Relief Shelter"
                            ),
                            "evacuees_allocated": shelter_alloc,
                            "remaining_capacity": max(0, cap - occ - shelter_alloc),
                        }
                    )

        # Calculate unfulfilled demand
        unfulfilled_demands: list[dict[str, Any]] = []
        for i_idx, inc in enumerate(incidents):
            pump_missing = (i_idx not in assigned_incident_pumps) and (
                inc.get("category") == "WATERLOGGING"
            )
            team_missing = i_idx not in assigned_incident_teams
            if pump_missing or team_missing:
                unfulfilled_demands.append(
                    {
                        "incident_id": inc.get("incident_id"),
                        "title": inc.get("title"),
                        "severity": inc.get("severity"),
                        "missing_pump": pump_missing,
                        "missing_team": team_missing,
                        "reason": "Insufficient ready resources available in proximity",
                    }
                )

        for d_idx, demand in enumerate(evacuation_demands):
            allocated = allocated_demands.get(d_idx, 0)
            needed = demand.get("people_count", 0)
            if allocated < needed:
                unfulfilled_demands.append(
                    {
                        "demand_id": demand.get("demand_id", f"DEMAND-{d_idx}"),
                        "location_name": demand.get("location_name", "Evacuation Zone"),
                        "unfulfilled_people": needed - allocated,
                        "reason": "Shelter capacity exhaustion in zone",
                    }
                )

        # Constraint violations (if solver status is INFEASIBLE or MODEL_INVALID)
        constraint_violations: list[str] = []
        if status not in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            constraint_violations.append(
                f"Solver returned status {status}; relaxing soft constraints suggested."
            )

        objective_score = (
            solver.Objective().Value()
            if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]
            else 0.0
        )

        return {
            "status": "OPTIMAL"
            if status == pywraplp.Solver.OPTIMAL
            else ("FEASIBLE" if status == pywraplp.Solver.FEASIBLE else "INFEASIBLE"),
            "solver_engine": "Google OR-Tools MIP (SCIP/CBC)",
            "objective_score": round(objective_score, 2),
            "suggested_allocation_plan": {
                "pump_allocations": suggested_pumps,
                "team_allocations": suggested_teams,
                "shelter_allocations": suggested_shelters,
            },
            "unfulfilled_demand": unfulfilled_demands,
            "constraint_violations": constraint_violations,
            "policy_rules": {
                "auto_dispatch": False,
                "human_approval_required": True,
                "notice": "Never auto-dispatch. An authorized human operator must review and confirm before dispatching responder tasks.",
            },
        }


resource_optimization_engine = ResourceOptimizationEngine()
