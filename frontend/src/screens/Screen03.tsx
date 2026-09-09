import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen03SignUp = () => {
  const { navigate, setUser } = useAppRouter();
  const [role, setRole] = useState('Student');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  return (
    <AuthContainer title="Create an account" subtitle="Join the OAU research network">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); const mappedRole = role === 'Supervisor / Faculty' ? 'faculty' : role === 'Researcher / Alumni' ? 'researcher' : 'student'; setUser({ id: `demo-${Date.now()}`, name: name || 'OAU Researcher', email: email || 'student@student.oauife.edu.ng', role: mappedRole }); navigate('discover'); }}>
        <Input label="Full Name" placeholder="John Doe" value={name} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)} />
        <Input label="OAU Email" type="email" placeholder="student@student.oauife.edu.ng" value={email} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} />
        <div className="flex flex-col space-y-1.5">
          <label className="text-sm font-medium text-slate-700">Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value)} className="px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-1 focus:ring-[#00502F] focus:border-[#00502F] sm:text-sm bg-white">
            <option>Student</option>
            <option>Researcher / Alumni</option>
            <option>Supervisor / Faculty</option>
          </select>
        </div>
        <Input label="Password" type="password" />
        <Button type="submit" className="w-full mt-6">Create Account</Button>
      </form>
    </AuthContainer>
  );
};

export default Screen03SignUp;
