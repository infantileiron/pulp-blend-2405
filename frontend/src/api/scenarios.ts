import {request} from "./client";export const fetchScenarios=()=>request("/scenarios");export const createScenarios=(body:unknown)=>request("/scenarios","POST",body);
