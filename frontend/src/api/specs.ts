import {request} from "./client";export const fetchSpecs=()=>request("/specs");export const createSpecs=(body:unknown)=>request("/specs","POST",body);
