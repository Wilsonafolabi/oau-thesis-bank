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

const Screen17AIProcessing = () => {
  const { navigate } = useAppRouter();
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setProgress(p => {
        if (p >= 100) {
          clearInterval(timer);
          setTimeout(() => navigate('publish-confirmation'), 1000);
          return 100;
        }
        return p + 10;
      });
    }, 400);
    return () => clearInterval(timer);
  }, [navigate]);

  return (
    <AuthenticatedLayout title="Processing Document">
      <div className="max-w-3xl mx-auto text-center mt-20">
        <UploadWizardNav step={4} />
        <div className="mb-8">
          <div className="w-24 h-24 mx-auto border-4 border-slate-100 border-t-[#00502F] rounded-full animate-spin"></div>
        </div>
        <h2 className="text-2xl font-bold text-slate-900 mb-2">AI is analyzing your thesis...</h2>
        <p className="text-slate-500 mb-8">Extracting semantic meaning, building search indexes, and generating summaries.</p>
        
        <div className="max-w-md mx-auto bg-slate-100 rounded-full h-2 mb-4 overflow-hidden">
          <motion.div className="h-full bg-[#00502F]" initial={{ width: 0 }} animate={{ width: `${progress}%` }} />
        </div>
        
        <div className="space-y-3 text-sm text-left max-w-md mx-auto bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center text-emerald-700"><CheckCircle className="w-4 h-4 mr-2"/> Text Extraction Complete</div>
          <div className={`flex items-center ${progress > 30 ? 'text-emerald-700' : 'text-slate-400'}`}>{progress > 30 ? <CheckCircle className="w-4 h-4 mr-2"/> : <div className="w-4 h-4 mr-2 border-2 border-slate-300 border-t-slate-500 rounded-full animate-spin"/>} Generating Abstract Summary</div>
          <div className={`flex items-center ${progress > 70 ? 'text-emerald-700' : 'text-slate-400'}`}>{progress > 70 ? <CheckCircle className="w-4 h-4 mr-2"/> : <div className="w-2 h-2 rounded-full bg-slate-300 mr-4 ml-1"/>} Building Semantic Vectors</div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen17AIProcessing;
