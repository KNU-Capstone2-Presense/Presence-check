import { defineConfig } from 'vite';
import fs from 'node:fs';
export default defineConfig(({command})=>({base:command==='build'?'/student/':'/',server:{https:process.env.TLS_CERT&&process.env.TLS_KEY?{cert:fs.readFileSync(process.env.TLS_CERT),key:fs.readFileSync(process.env.TLS_KEY)}:undefined}}));
