import React, { useMemo, useState } from 'react';
import { MoreVertical, Search, Shield, UserCheck, UserX, Users, ChevronDown } from 'lucide-react';
import { useAppRouter, AuthenticatedLayout, Card, Badge, Button } from '../components/shared';

const initialUsers = [
  {id:'U-4021',name:'Adekunle Ojo',email:'ojo@student.oauife.edu.ng',role:'Alumni',status:'Active',joined:'Aug 2025'},
  {id:'U-1188',name:'Dr. O. A. Fajemisin',email:'ofajemisin@oauife.edu.ng',role:'Faculty',status:'Active',joined:'Mar 2024'},
  {id:'U-9102',name:'Oluwaseun Adetunji',email:'adetunji@student.oauife.edu.ng',role:'Student',status:'Active',joined:'Jan 2026'},
  {id:'U-5510',name:'Unknown User',email:'test@gmail.com',role:'Student',status:'Suspended',joined:'Jun 2026'},
  {id:'U-2210',name:'Prof. E. R. Adagunodo',email:'adagunodo@oauife.edu.ng',role:'Faculty',status:'Active',joined:'Nov 2023'},
];

const Screen45UserManagement = () => {
 const {navigate}=useAppRouter(); const [users,setUsers]=useState(initialUsers); const [q,setQ]=useState('');
 const filtered=useMemo(()=>users.filter(u=>`${u.name} ${u.email} ${u.role}`.toLowerCase().includes(q.toLowerCase())),[users,q]);
 const toggle=(id)=>setUsers(v=>v.map(u=>u.id===id?{...u,status:u.status==='Active'?'Suspended':'Active'}:u));
 return <AuthenticatedLayout title="User Management" admin><div className="max-w-7xl mx-auto space-y-6">
   <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4"><div><Badge variant="green">8,201 active users</Badge><h2 className="mt-2 text-2xl font-bold">People & access</h2><p className="mt-1 text-sm text-slate-500">Manage roles, account status and repository access.</p></div><Button onClick={()=>navigate('admin-dashboard')}>Back to dashboard</Button></div>
   <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">{[{icon:Users,value:'8,201',label:'Active users'},{icon:UserCheck,value:'3,912',label:'Researchers'},{icon:UserX,value:'24',label:'Suspended'}].map((s)=>{const I=s.icon; return <Card key={s.label} className="p-5"><I className="h-4 w-4 text-[#00502F]"/><p className="mt-4 text-2xl font-bold">{s.value}</p><p className="mt-1 text-xs text-slate-500">{s.label}</p></Card>})}</div>
   <Card className="overflow-hidden"><div className="p-4 border-b border-slate-200 flex flex-col md:flex-row gap-3"><div className="relative flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400"/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search by name, email or role..." className="w-full pl-9 pr-3 py-2.5 border border-slate-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-emerald-100"/></div><button className="inline-flex items-center gap-2 justify-center px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-600">All roles <ChevronDown className="h-4 w-4"/></button></div>
   <div className="overflow-x-auto"><table className="min-w-[760px] w-full"><thead className="bg-slate-50"><tr>{['User','Role','Status','Joined',''].map(h=><th key={h} className="px-5 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{filtered.map(u=><tr key={u.id} className="hover:bg-slate-50/70"><td className="px-5 py-4"><div className="flex items-center gap-3"><span className="h-9 w-9 rounded-full bg-emerald-50 text-[#00502F] flex items-center justify-center text-xs font-bold">{u.name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span><div><p className="text-sm font-semibold">{u.name}</p><p className="text-xs text-slate-500">{u.email}</p></div></div></td><td className="px-5 py-4"><Badge variant={u.role==='Faculty'?'gold':'gray'}>{u.role}</Badge></td><td className="px-5 py-4"><Badge variant={u.status==='Active'?'green':'gray'}>{u.status}</Badge></td><td className="px-5 py-4 text-xs text-slate-500">{u.joined}</td><td className="px-5 py-4 text-right"><div className="inline-flex items-center gap-2"><button className="px-2.5 py-1.5 text-xs font-semibold text-[#00502F] rounded-lg hover:bg-emerald-50">Edit role</button><button onClick={()=>toggle(u.id)} className={`px-2.5 py-1.5 text-xs font-semibold rounded-lg ${u.status==='Active'?'text-red-600 hover:bg-red-50':'text-emerald-700 hover:bg-emerald-50'}`}>{u.status==='Active'?'Suspend':'Restore'}</button><button className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400"><MoreVertical className="h-4 w-4"/></button></div></td></tr>)}</tbody></table></div></Card>
   <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-start gap-3"><Shield className="h-5 w-5 text-[#00502F] mt-0.5"/><div><p className="text-sm font-semibold">Role-based access is ready for backend integration</p><p className="text-xs text-slate-500 mt-1">The frontend separates student/researcher and administrator experiences. Your backend should enforce the actual permissions.</p></div></div>
 </div></AuthenticatedLayout>;
};
export default Screen45UserManagement;
