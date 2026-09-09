import React, { useMemo, useState } from 'react';
import {
  Activity, AlertCircle, ArrowUpRight, Bot, CheckCircle2, Clock3, Database,
  FileCheck2, FileText, Gauge, HardDrive, HeartPulse, RefreshCw, Search,
  Server, ShieldAlert, ShieldCheck, Sparkles, TrendingUp, UserPlus, Users,
  Wifi, XCircle
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { motion } from 'framer-motion';
import { useAppRouter, AuthenticatedLayout, Card, Badge, Button } from '../components/shared';

const trend = [
  { name: 'Mon', uploads: 46, users: 28, views: 620 }, { name: 'Tue', uploads: 61, users: 34, views: 740 },
  { name: 'Wed', uploads: 54, users: 31, views: 680 }, { name: 'Thu', uploads: 72, users: 42, views: 890 },
  { name: 'Fri', uploads: 66, users: 38, views: 820 }, { name: 'Sat', uploads: 39, users: 22, views: 510 },
  { name: 'Sun', uploads: 31, users: 18, views: 430 },
];

const faculties = [
  { name: 'Science', value: 32 }, { name: 'Technology', value: 24 }, { name: 'Arts', value: 18 },
  { name: 'Social Sciences', value: 15 }, { name: 'Health Sciences', value: 11 },
];

const initialActivity = [
  ['2 min ago', 'New thesis uploaded', 'Machine Learning for Crop Yield Prediction', 'Review queue', 'warning'],
  ['7 min ago', 'AI processing completed', 'Yoruba Proverbs Database', 'Indexed successfully', 'success'],
  ['12 min ago', 'Thesis approved', 'Mobile Banking Adoption in Rural Communities', 'Published', 'success'],
  ['18 min ago', 'New researcher registered', 'O. Adetunji', 'Account created', 'info'],
  ['25 min ago', 'Content reported', 'Analysis of Soil pH using Sensor Networks', 'Needs review', 'danger'],
];

const serviceStatus = [
  { label: 'API Gateway', value: 'Operational', icon: Server, state: 'good', latency: '84 ms' },
  { label: 'Database', value: 'Operational', icon: Database, state: 'good', latency: '42 ms' },
  { label: 'AI / RAG', value: 'Operational', icon: Bot, state: 'good', latency: '1.8 s' },
  { label: 'File Storage', value: 'Operational', icon: HardDrive, state: 'good', latency: '99.98%' },
];

const Screen43AdminDashboard = () => {
  const { navigate } = useAppRouter();
  const [range, setRange] = useState('7 days');
  const [refreshing, setRefreshing] = useState(false);
  const [activity, setActivity] = useState(initialActivity);

  const stats = useMemo(() => [
    { label: 'Total theses', value: '12,450', change: '+8.2%', icon: FileText, tone: 'green', detail: 'repository records' },
    { label: 'Active users', value: '8,201', change: '+4.7%', icon: Users, tone: 'blue', detail: 'last 30 days' },
    { label: 'Pending review', value: '45', change: '12 high', icon: Clock3, tone: 'gold', detail: 'moderation queue' },
    { label: 'System health', value: '99.9%', change: 'All clear', icon: HeartPulse, tone: 'green', detail: 'service availability' },
  ], []);

  const refresh = () => {
    setRefreshing(true);
    window.setTimeout(() => setRefreshing(false), 700);
  };

  return (
    <AuthenticatedLayout title="Admin Dashboard" admin>
      <div className="max-w-7xl mx-auto space-y-6 pb-10">
        <div className="flex flex-col xl:flex-row xl:items-end xl:justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2"><Badge variant="green">Operations center</Badge><span className="inline-flex items-center gap-1.5 text-[11px] text-emerald-700"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse"/> Live monitoring</span><span className="text-[10px] font-semibold uppercase tracking-wider text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">Frontend demo mode</span></div>
            <h2 className="mt-2 text-2xl sm:text-3xl font-bold tracking-tight">Platform control center</h2>
            <p className="mt-1 text-sm text-slate-500 max-w-2xl">Monitor repository activity, moderation, users, AI processing and core services from one place. Demo values will be replaced by backend APIs.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={refresh}><RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`}/> Refresh</Button>
            <Button variant="secondary" onClick={() => navigate('content-moderation')}>Moderation <ArrowUpRight className="ml-2 h-4 w-4"/></Button>
            <Button onClick={() => navigate('user-management')}>Manage users</Button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {stats.map((s, i) => { const I = s.icon; return (
            <motion.div key={s.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * .05 }}>
              <Card className="p-5 hover:-translate-y-0.5 transition-transform">
                <div className="flex justify-between items-start"><span className={`h-10 w-10 rounded-xl flex items-center justify-center ${s.tone === 'gold' ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-[#00502F]'}`}><I className="h-5 w-5"/></span><span className="text-[11px] font-semibold text-emerald-700">{s.change}</span></div>
                <p className="mt-5 text-2xl font-bold tracking-tight">{s.value}</p><p className="mt-1 text-xs font-semibold text-slate-700">{s.label}</p><p className="mt-1 text-[11px] text-slate-500">{s.detail}</p>
              </Card>
            </motion.div>
          ); })}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.65fr_1fr] gap-6">
          <Card className="p-5 sm:p-6">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
              <div><div className="flex items-center gap-2"><h3 className="font-bold">Platform activity</h3><span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{range}</span></div><p className="text-xs text-slate-500 mt-1">Uploads, new users and repository views.</p></div>
              <div className="flex rounded-lg border border-slate-200 p-0.5 bg-slate-50">{['7 days','30 days','90 days'].map(x => <button key={x} onClick={() => setRange(x)} className={`px-2.5 py-1.5 rounded-md text-[11px] font-semibold ${range === x ? 'bg-white shadow-sm text-[#00502F]' : 'text-slate-500'}`}>{x}</button>)}</div>
            </div>
            <div className="h-72 mt-5"><ResponsiveContainer width="100%" height="100%"><AreaChart data={trend}><defs><linearGradient id="adminFill2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#00502F" stopOpacity={0.16}/><stop offset="100%" stopColor="#00502F" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0"/><XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill:'#64748B', fontSize:11 }}/><YAxis axisLine={false} tickLine={false} tick={{ fill:'#64748B', fontSize:11 }}/><Tooltip/><Area type="monotone" dataKey="views" stroke="#00502F" strokeWidth={2.5} fill="url(#adminFill2)"/><Area type="monotone" dataKey="uploads" stroke="#B08D2C" strokeWidth={2} fill="transparent"/></AreaChart></ResponsiveContainer></div>
            <div className="flex gap-5 text-[11px] text-slate-500"><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-[#00502F]"/> Views</span><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-[#B08D2C]"/> Uploads</span></div>
          </Card>

          <Card className="p-5 sm:p-6">
            <div className="flex items-start justify-between"><div><h3 className="font-bold">Moderation & alerts</h3><p className="text-xs text-slate-500 mt-1">Items requiring admin attention.</p></div><ShieldAlert className="h-5 w-5 text-amber-500"/></div>
            <div className="mt-5 space-y-2.5">
              {[['12','High-priority flags','AI similarity / content reports','gold'],['33','Standard reviews','Metadata and supervisor checks','gray'],['18','Access requests','Restricted thesis requests','blue'],['5','System alerts','Jobs needing inspection','red']].map(([count,title,desc,tone]) => <button key={title} onClick={() => navigate('content-moderation')} className="w-full text-left rounded-xl border border-slate-200 p-3.5 hover:border-slate-300 hover:bg-slate-50 transition"><div className="flex items-center gap-3"><span className={`text-lg font-bold ${tone==='red'?'text-red-600':tone==='gold'?'text-amber-700':'text-[#00502F]'}`}>{count}</span><div className="min-w-0"><p className="text-sm font-semibold">{title}</p><p className="text-[11px] text-slate-500 mt-0.5 truncate">{desc}</p></div><ArrowUpRight className="ml-auto h-4 w-4 text-slate-300"/></div></button>)}
            </div>
            <button onClick={() => navigate('content-moderation')} className="mt-4 w-full text-xs font-semibold text-[#00502F] hover:underline">Open moderation center →</button>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="p-5 sm:p-6"><div className="flex items-center justify-between"><div><h3 className="font-bold">AI processing monitor</h3><p className="text-xs text-slate-500 mt-1">Current indexing and intelligence jobs.</p></div><Bot className="h-5 w-5 text-[#00502F]"/></div><div className="mt-5 grid grid-cols-3 gap-3">{[['3','Processing','text-amber-600'],['148','Completed','text-emerald-700'],['2','Needs retry','text-red-600']].map(([v,l,c])=><div key={l} className="rounded-xl bg-slate-50 border border-slate-100 p-4"><p className={`text-xl font-bold ${c}`}>{v}</p><p className="mt-1 text-[11px] text-slate-500">{l}</p></div>)}</div><div className="mt-5 space-y-3">{[['Thesis summaries','87%','emerald'],['Embeddings / indexing','64%','blue'],['Similarity checks','42%','amber']].map(([l,p,t])=><div key={l}><div className="flex justify-between text-[11px] mb-1.5"><span className="font-medium text-slate-700">{l}</span><span className="text-slate-400">{p}</span></div><div className="h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className={`h-full rounded-full ${t==='amber'?'bg-amber-500':t==='blue'?'bg-blue-500':'bg-emerald-600'}`} style={{width:p}}/></div></div>)}</div><Button variant="ghost" size="sm" className="mt-4" onClick={() => navigate('content-moderation')}>Inspect flagged jobs <ArrowUpRight className="ml-1 h-3.5 w-3.5"/></Button></Card>

          <Card className="p-5 sm:p-6"><div className="flex items-center justify-between"><div><h3 className="font-bold">Service health</h3><p className="text-xs text-slate-500 mt-1">Infrastructure signals from connected services.</p></div><Gauge className="h-5 w-5 text-slate-400"/></div><div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-2.5">{serviceStatus.map(s=>{const I=s.icon;return <div key={s.label} className="rounded-xl border border-slate-200 p-3.5"><div className="flex items-center gap-2.5"><span className="h-8 w-8 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center"><I className="h-4 w-4"/></span><div className="min-w-0"><p className="text-xs font-semibold">{s.label}</p><p className="text-[10px] text-slate-500 mt-0.5">{s.latency}</p></div><span className="ml-auto h-2 w-2 rounded-full bg-emerald-500"/></div><p className="mt-2 text-[10px] font-medium text-emerald-700">{s.value}</p></div>})}</div><div className="mt-4 flex items-center gap-2 text-[11px] text-slate-500"><Wifi className="h-3.5 w-3.5"/> Last checked just now <span className="text-slate-300">•</span> 4/4 services healthy</div></Card>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_1fr] gap-6">
          <Card className="p-5 sm:p-6"><div className="flex items-center justify-between"><div><h3 className="font-bold">Research distribution</h3><p className="text-xs text-slate-500 mt-1">Published theses by faculty.</p></div><TrendingUp className="h-5 w-5 text-slate-400"/></div><div className="h-64 mt-4"><ResponsiveContainer width="100%" height="100%"><BarChart data={faculties} layout="vertical" margin={{ left: 8, right: 12 }}><CartesianGrid strokeDasharray="3 3" horizontal={false}/><XAxis type="number" hide/><YAxis dataKey="name" type="category" axisLine={false} tickLine={false} width={92} tick={{ fill:'#64748B', fontSize:10 }}/><Tooltip/><Bar dataKey="value" fill="#00502F" radius={[0,5,5,0]} /></BarChart></ResponsiveContainer></div></Card>

          <Card className="overflow-hidden"><div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between"><div><h3 className="font-bold">Live activity</h3><p className="text-xs text-slate-500 mt-1">Most recent platform events.</p></div><Activity className="h-5 w-5 text-slate-400"/></div><div className="divide-y divide-slate-100">{activity.map(([time,title,subject,status,type])=><div key={time+title} className="p-4 flex items-start gap-3"><span className={`mt-0.5 h-8 w-8 rounded-lg flex items-center justify-center ${type==='danger'?'bg-red-50 text-red-600':type==='warning'?'bg-amber-50 text-amber-600':type==='info'?'bg-blue-50 text-blue-600':'bg-emerald-50 text-emerald-700'}`}>{type==='danger'?<AlertCircle className="h-4 w-4"/>:type==='warning'?<Clock3 className="h-4 w-4"/>:type==='info'?<UserPlus className="h-4 w-4"/>:<CheckCircle2 className="h-4 w-4"/>}</span><div className="flex-1 min-w-0"><div className="flex justify-between gap-2"><p className="text-xs font-semibold truncate">{title}</p><span className="text-[10px] text-slate-400 whitespace-nowrap">{time}</span></div><p className="text-[11px] text-slate-500 mt-1 truncate">{subject}</p><p className="text-[10px] text-slate-400 mt-1">{status}</p></div></div>)}</div><button onClick={()=>setActivity(v=>[...v].reverse())} className="w-full py-3 text-[11px] font-semibold text-[#00502F] hover:bg-slate-50">Refresh activity feed</button></Card>
        </div>

        <div className="rounded-2xl bg-[#0B3D2E] text-white p-5 sm:p-6 flex flex-col md:flex-row md:items-center gap-4 justify-between"><div><div className="flex items-center gap-2 text-xs font-semibold text-emerald-200"><Sparkles className="h-4 w-4"/> ADMIN CONTROL CENTER</div><h3 className="mt-2 text-lg font-bold">Keep the repository trustworthy.</h3><p className="mt-1 text-xs text-emerald-100/70 max-w-xl">Use moderation, user management and activity monitoring together to keep research discoverable, safe and properly governed.</p></div><div className="flex gap-2"><Button onClick={()=>navigate('content-moderation')} className="bg-white text-[#0B3D2E] hover:bg-slate-100">Review queue</Button><Button variant="ghost" className="text-white hover:bg-white/10" onClick={()=>navigate('user-management')}>Users</Button></div></div>
      </div>
    </AuthenticatedLayout>
  );
};
export default Screen43AdminDashboard;
