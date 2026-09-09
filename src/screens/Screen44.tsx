import React, { useState } from 'react';
import { AlertTriangle, Check, Eye, Filter, Search, ShieldAlert, X } from 'lucide-react';
import { motion } from 'framer-motion';
import { useAppRouter, AuthenticatedLayout, Card, Badge, Button } from '../components/shared';

const initialItems = [
  { id:'M-1042', title:'Analysis of Soil pH using Sensor Networks', author:'Student U.492', dept:'Agricultural Engineering', flag:'High similarity', score:'78%', note:'Structural similarity detected against thesis ID #9923.', status:'Pending' },
  { id:'M-1041', title:'Yoruba Proverbs Database', author:'Student U.102', dept:'Faculty of Arts', flag:'Standard review', score:'—', note:'Awaiting standard metadata verification.', status:'Pending' },
  { id:'M-1040', title:'Mobile Banking Adoption in Rural Communities', author:'Student U.881', dept:'Economics', flag:'Metadata', score:'—', note:'Supervisor confirmation is missing.', status:'Pending' },
];

const Screen44ContentModeration = () => {
  const { navigate } = useAppRouter();
  const [items,setItems]=useState(initialItems);
  const [query,setQuery]=useState('');
  const action=(id,status)=>setItems(v=>v.map(x=>x.id===id?{...x,status}:x));
  const visible=items.filter(x=>`${x.title} ${x.author} ${x.dept}`.toLowerCase().includes(query.toLowerCase()));
  return <AuthenticatedLayout title="Content Moderation" admin><div className="max-w-7xl mx-auto space-y-6">
    <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4"><div><Badge variant="gold">12 high-priority flags</Badge><h2 className="mt-2 text-2xl font-bold">Review queue</h2><p className="mt-1 text-sm text-slate-500">Validate research submissions before they become part of the official repository.</p></div><div className="flex gap-2"><Button variant="secondary" onClick={()=>navigate('admin-dashboard')}>Dashboard</Button><Button onClick={()=>navigate('user-management')}>Users</Button></div></div>
    <Card className="p-3 sm:p-4"><div className="flex flex-col sm:flex-row gap-3"><div className="relative flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400"/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search submissions..." className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-emerald-100 focus:border-[#00502F]"/></div><button className="inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-medium text-slate-600"><Filter className="h-4 w-4"/> All flags</button></div></Card>
    <div className="space-y-4">{visible.map((item,i)=><motion.div key={item.id} initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} transition={{delay:i*.05}}><Card className="p-5"><div className="flex flex-col xl:flex-row xl:items-start gap-5"><div className="flex-1"><div className="flex flex-wrap items-center gap-2"><Badge variant={item.flag==='High similarity'?'gold':'blue'}>{item.flag}</Badge>{item.score!=='—'&&<Badge variant="gray">{item.score} match</Badge>}<span className="text-[11px] text-slate-400">{item.id}</span></div><h3 className="mt-3 font-bold text-slate-900">{item.title}</h3><p className="mt-1 text-xs text-slate-500">{item.author} · {item.dept}</p><div className="mt-4 rounded-xl bg-slate-50 border border-slate-100 p-3 flex gap-3"><ShieldAlert className="h-4 w-4 text-amber-600 mt-0.5 shrink-0"/><p className="text-xs leading-5 text-slate-600"><span className="font-semibold text-slate-800">Review note:</span> {item.note}</p></div></div><div className="xl:w-64 flex xl:flex-col gap-2"><Button variant="secondary" className="flex-1" onClick={()=>navigate('thesis-detail')}><Eye className="h-4 w-4 mr-2"/> Review document</Button>{item.status==='Pending' ? <><Button className="flex-1" onClick={()=>action(item.id,'Approved')}><Check className="h-4 w-4 mr-2"/> Approve</Button><Button variant="ghost" className="flex-1 text-red-600 hover:bg-red-50" onClick={()=>action(item.id,'Rejected')}><X className="h-4 w-4 mr-2"/> Reject</Button></> : <Badge variant={item.status==='Approved'?'green':'gray'}>{item.status}</Badge>}</div></div></Card></motion.div>)}</div>
  </div></AuthenticatedLayout>;
};
export default Screen44ContentModeration;
