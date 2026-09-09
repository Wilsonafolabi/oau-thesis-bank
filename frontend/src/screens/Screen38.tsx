import React from 'react';
import { motion } from 'framer-motion';
import { BarChart2, Download, Eye, Search, ArrowUpRight, FileText, Users, Bookmark, TrendingUp } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useAppRouter, AuthenticatedLayout, Card, Badge, Button } from '../components/shared';

const monthly = [
  { name: 'Jan', views: 180, downloads: 42 }, { name: 'Feb', views: 240, downloads: 61 },
  { name: 'Mar', views: 320, downloads: 78 }, { name: 'Apr', views: 410, downloads: 96 },
  { name: 'May', views: 510, downloads: 124 }, { name: 'Jun', views: 620, downloads: 151 },
];

const projects = [
  { title: 'Machine Learning for Crop Yield Prediction in Nigeria', views: 890, downloads: 214, growth: '+18%' },
  { title: 'Natural Language Processing for Yoruba Text Classification', views: 530, downloads: 83, growth: '+11%' },
  { title: 'Predictive Modelling of Student Academic Performance', views: 310, downloads: 48, growth: '+7%' },
];

const Screen38PersonalAnalytics = () => {
  const { navigate } = useAppRouter();
  const stats = [
    { label: 'Total views', value: '1,420', change: '+12.4%', icon: Eye },
    { label: 'PDF downloads', value: '345', change: '+8.7%', icon: Download },
    { label: 'Search appearances', value: '2,890', change: '+21.3%', icon: Search },
    { label: 'Internal citations', value: '12', change: '+3 this month', icon: Bookmark },
  ];
  return (
    <AuthenticatedLayout title="My Research Analytics">
      <div className="max-w-7xl mx-auto space-y-6">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl bg-[#00502F] p-5 sm:p-7 text-white overflow-hidden relative">
          <div className="absolute -right-16 -top-20 h-64 w-64 rounded-full border border-white/10" />
          <div className="absolute right-8 -bottom-24 h-52 w-52 rounded-full border border-[#D4AF37]/20" />
          <div className="relative flex flex-col md:flex-row md:items-end md:justify-between gap-5">
            <div><Badge variant="gold">Personal research intelligence</Badge><h2 className="mt-3 text-2xl sm:text-3xl font-bold tracking-tight">See how your work travels.</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-emerald-100">Track discovery, readership and the signals that show where your research is creating value.</p></div>
            <Button variant="secondary" onClick={() => navigate('my-projects')}>View my projects <ArrowUpRight className="ml-2 h-4 w-4" /></Button>
          </div>
        </motion.div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {stats.map((s, i) => { const Icon = s.icon; return <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * .06 }}><Card className="p-5"><div className="flex items-center justify-between"><span className="h-9 w-9 rounded-lg bg-emerald-50 text-[#00502F] flex items-center justify-center"><Icon className="h-4 w-4" /></span><span className="text-xs font-semibold text-emerald-700">{s.change}</span></div><p className="mt-5 text-2xl font-bold tracking-tight">{s.value}</p><p className="mt-1 text-xs text-slate-500">{s.label}</p></Card></motion.div>; })}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.7fr_1fr] gap-6">
          <Card className="p-5 sm:p-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"><div><h3 className="font-bold text-slate-900">Research reach</h3><p className="text-xs text-slate-500 mt-1">Views and downloads across your published work</p></div><div className="flex items-center gap-4 text-xs text-slate-500"><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#00502F]" /> Views</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#D4AF37]" /> Downloads</span></div></div>
            <div className="h-72 mt-5"><ResponsiveContainer width="100%" height="100%"><AreaChart data={monthly}><defs><linearGradient id="viewsFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#00502F" stopOpacity={0.18}/><stop offset="100%" stopColor="#00502F" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0"/><XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748B', fontSize: 12 }}/><YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748B', fontSize: 12 }}/><Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #E2E8F0' }}/><Area type="monotone" dataKey="views" stroke="#00502F" strokeWidth={2.5} fill="url(#viewsFill)"/><Area type="monotone" dataKey="downloads" stroke="#D4AF37" strokeWidth={2} fill="none"/></AreaChart></ResponsiveContainer></div>
          </Card>
          <Card className="p-5 sm:p-6"><div className="flex items-center justify-between"><div><h3 className="font-bold">Discovery funnel</h3><p className="text-xs text-slate-500 mt-1">Where readers found you</p></div><BarChart2 className="h-5 w-5 text-slate-400" /></div><div className="h-56 mt-4"><ResponsiveContainer width="100%" height="100%"><BarChart data={[{name:'Search',value:65},{name:'Profiles',value:25},{name:'AI',value:10}]} layout="vertical"><XAxis type="number" hide/><YAxis type="category" dataKey="name" width={65} axisLine={false} tickLine={false} tick={{fontSize:11,fill:'#64748B'}}/><Tooltip/><Bar dataKey="value" fill="#00502F" radius={[0,5,5,0]} /></BarChart></ResponsiveContainer></div></Card>
        </div>

        <Card className="p-5 sm:p-6"><div className="flex items-center justify-between mb-5"><div><h3 className="font-bold">Top performing projects</h3><p className="text-xs text-slate-500 mt-1">Your most discovered research</p></div><TrendingUp className="h-5 w-5 text-[#D4AF37]" /></div><div className="divide-y divide-slate-100">{projects.map((p) => <button key={p.title} onClick={() => navigate('thesis-analytics')} className="w-full py-4 flex flex-col sm:flex-row sm:items-center gap-3 text-left hover:bg-slate-50 rounded-xl px-2 transition"><span className="h-9 w-9 rounded-lg bg-slate-100 flex items-center justify-center shrink-0"><FileText className="h-4 w-4 text-slate-500" /></span><span className="flex-1 min-w-0"><span className="block text-sm font-semibold text-slate-800 truncate">{p.title}</span><span className="block text-xs text-slate-500 mt-1">{p.views} views · {p.downloads} downloads</span></span><span className="text-xs font-semibold text-emerald-700">{p.growth}</span><ArrowUpRight className="h-4 w-4 text-slate-400" /></button>)}</div></Card>
      </div>
    </AuthenticatedLayout>
  );
};
export default Screen38PersonalAnalytics;
