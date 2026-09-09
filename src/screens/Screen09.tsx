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

const Screen09ThesisDetail = () => {
  const { navigate } = useAppRouter();
  const thesis = MOCK_THESES[0];
  
  return (
    <AuthenticatedLayout title="Thesis Details">
      <div className="max-w-6xl mx-auto flex flex-col lg:flex-row gap-8">
        {/* Main Content */}
        <div className="flex-1 space-y-8">
          <div>
            <div className="flex items-center space-x-3 mb-4">
              <Badge variant="green">Published 2023</Badge>
              <span className="text-sm text-slate-500 flex items-center"><FileText className="w-4 h-4 mr-1"/> 145 pages</span>
            </div>
            <h1 className="text-3xl font-bold text-slate-900 leading-tight mb-4">{thesis.title}</h1>
            <p className="text-lg text-slate-700">by <span className="font-medium text-[#00502F] cursor-pointer hover:underline" onClick={() => navigate('researcher-profile')}>{thesis.author}</span></p>
          </div>

          <div className="flex space-x-4">
            <Button onClick={() => navigate('pdf-reader')}><BookOpen className="w-4 h-4 mr-2"/> Read Document</Button>
            <Button variant="secondary" onClick={() => navigate('thesis-ai')}><Cpu className="w-4 h-4 mr-2"/> AI Summary</Button>
            <Button variant="ghost"><Bookmark className="w-4 h-4 mr-2"/> Save</Button>
          </div>

          <div className="prose prose-slate max-w-none">
            <h3 className="text-xl font-semibold border-b border-slate-200 pb-2">Abstract</h3>
            <p className="text-slate-600 leading-relaxed mt-4">{thesis.abstract} Further details outline the methodology, utilizing extensive datasets collected over a 5-year period. The results indicate a 15% improvement in prediction accuracy compared to traditional baseline models.</p>
            
            <h3 className="text-xl font-semibold border-b border-slate-200 pb-2 mt-8">Research Objectives</h3>
            <ul className="list-disc pl-5 text-slate-600 mt-4 space-y-2">
              <li>To evaluate historical crop yield data.</li>
              <li>To train machine learning models for prediction.</li>
              <li>To assess the impact of climate variables.</li>
            </ul>
          </div>
        </div>

        {/* Sidebar */}
        <div className="w-full lg:w-80 space-y-6">
          <Card className="p-6 bg-slate-50 border-none">
            <h4 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-4">Metadata</h4>
            <div className="space-y-4 text-sm">
              <div>
                <span className="block text-slate-500 mb-1">Department</span>
                <span className="font-medium text-slate-900">{thesis.dept}</span>
              </div>
              <div>
                <span className="block text-slate-500 mb-1">Supervisor</span>
                <span className="font-medium text-[#00502F] cursor-pointer hover:underline">{thesis.supervisor}</span>
              </div>
              <div>
                <span className="block text-slate-500 mb-1">Methodology</span>
                <span className="font-medium text-slate-900">Quantitative, Regression Analysis</span>
              </div>
            </div>
          </Card>
          
          <Card className="p-6">
            <h4 className="text-sm font-bold text-slate-900 mb-4 flex items-center"><GitBranch className="w-4 h-4 mr-2 text-[#D4AF37]"/> Impact Network</h4>
            <div className="space-y-3">
              <button onClick={() => navigate('thesis-discussion')} className="w-full flex justify-between items-center text-sm text-slate-600 hover:text-[#00502F] p-2 hover:bg-slate-50 rounded">
                <span>Discussions</span> <Badge variant="gray">4</Badge>
              </button>
              <button onClick={() => navigate('research-lineage')} className="w-full flex justify-between items-center text-sm text-slate-600 hover:text-[#00502F] p-2 hover:bg-slate-50 rounded">
                <span>View Lineage</span> <ArrowRight className="w-4 h-4"/>
              </button>
              <button onClick={() => navigate('thesis-analytics')} className="w-full flex justify-between items-center text-sm text-slate-600 hover:text-[#00502F] p-2 hover:bg-slate-50 rounded">
                <span>Analytics</span> <BarChart2 className="w-4 h-4"/>
              </button>
            </div>
          </Card>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen09ThesisDetail;
