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

const Screen32CollaborationHub = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Collaboration Hub">
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* Hero */}
        <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-xl p-8 text-white flex justify-between items-center shadow-lg">
          <div>
            <h2 className="text-2xl font-bold mb-2">Connect and create impact</h2>
            <p className="text-slate-300">Find co-authors, request datasets, or seek mentorship from OAU alumni.</p>
          </div>
          <Button variant="secondary" onClick={() => navigate('collab-opportunity')}>Post Opportunity</Button>
        </div>

        {/* Tabs */}
        <div className="flex space-x-6 border-b border-slate-200">
          <button className="pb-3 border-b-2 border-[#00502F] font-medium text-sm text-[#00502F]">Open Opportunities</button>
          <button className="pb-3 border-b-2 border-transparent text-slate-500 font-medium text-sm">Find Mentors</button>
          <button className="pb-3 border-b-2 border-transparent text-slate-500 font-medium text-sm">My Requests</button>
        </div>

        {/* Listings */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[
            { type: 'Co-Author Needed', title: 'Expanding NLP dataset for Yoruba Dialects', author: 'Prof. Adagunodo', tag: 'Computer Science' },
            { type: 'Data Request', title: 'Need access to structural integrity data (Civil Eng 2018-2022)', author: 'John Doe', tag: 'Civil Engineering' }
          ].map((opp, i) => (
            <Card key={i} hover className="p-6" onClick={() => navigate('collab-opportunity')}>
              <div className="flex justify-between items-start mb-3">
                <Badge variant={i===0 ? 'gold' : 'blue'}>{opp.type}</Badge>
                <span className="text-xs text-slate-400">2 days ago</span>
              </div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">{opp.title}</h3>
              <p className="text-sm text-slate-500 mb-4">Posted by {opp.author} • {opp.tag}</p>
              <Button variant="secondary" className="w-full text-sm">View Details</Button>
            </Card>
          ))}
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen32CollaborationHub;
