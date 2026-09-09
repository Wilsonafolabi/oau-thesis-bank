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

const Screen29Researchers = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Researcher Directory">
      <div className="flex flex-col md:flex-row gap-6 mb-8">
        <div className="flex-1 relative">
          <SearchIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 w-5 h-5"/>
          <input type="text" placeholder="Search by name, department, or research interest..." className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-1 focus:ring-[#00502F]" />
        </div>
        <select className="border border-slate-300 rounded-md p-2 bg-white text-sm"><option>All Departments</option><option>Computer Science</option></select>
        <select className="border border-slate-300 rounded-md p-2 bg-white text-sm"><option>All Roles</option><option>Faculty</option><option>Alumni</option></select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {MOCK_USERS.map((user, i) => (
          <Card key={user.id} hover className="p-6 text-center" onClick={() => navigate('researcher-profile')}>
            <div className="w-20 h-20 mx-auto rounded-full bg-[#00502F] text-white flex items-center justify-center text-2xl font-bold mb-4">
              {user.avatar}
            </div>
            <h3 className="text-lg font-bold text-slate-900">{user.name}</h3>
            <p className="text-sm text-[#D4AF37] font-medium mb-1">{user.role}</p>
            <p className="text-xs text-slate-500 mb-4">{user.dept}</p>
            <div className="flex flex-wrap justify-center gap-1 mb-6">
              {['Machine Learning', 'Data Science', 'Python'].slice(0, i+1).map(skill => (
                 <span key={skill} className="px-2 py-1 bg-slate-100 text-slate-600 rounded-full text-xs">{skill}</span>
              ))}
            </div>
            <Button variant="secondary" className="w-full text-sm" onClick={(e) => { e.stopPropagation(); navigate('messages'); }}>Message</Button>
          </Card>
        ))}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen29Researchers;
