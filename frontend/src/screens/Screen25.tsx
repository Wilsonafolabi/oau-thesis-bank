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

const Screen25GapExplorer = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Research Gap Explorer">
      <div className="space-y-8">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <p className="text-slate-600 max-w-2xl">Discover under-researched areas and frequent limitations cited by OAU researchers. These represent opportunities for novel projects.</p>
          <div className="flex space-x-2">
            <select className="border border-slate-300 rounded-md text-sm p-2 bg-white"><option>All Faculties</option></select>
            <select className="border border-slate-300 rounded-md text-sm p-2 bg-white"><option>Last 5 Years</option></select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="p-6 col-span-1 md:col-span-2">
            <h3 className="text-lg font-semibold text-slate-900 mb-6">Trending "Future Work" Recommendations</h3>
            <div className="h-64 flex items-end space-x-4">
              {/* Fake chart bars */}
              {[40, 70, 45, 90, 60].map((h, i) => (
                <div key={i} className="flex-1 flex flex-col justify-end group relative">
                  <div className="absolute -top-8 left-1/2 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 bg-slate-800 text-white text-xs py-1 px-2 rounded transition-opacity whitespace-nowrap">Mentions: {h}</div>
                  <div className="w-full bg-[#00502F] rounded-t-sm transition-all duration-300 group-hover:bg-[#D4AF37]" style={{height: `${h}%`}}></div>
                </div>
              ))}
            </div>
            <div className="flex text-xs text-slate-500 mt-3 text-center">
              <span className="flex-1">Real-time Data</span>
              <span className="flex-1">Larger Sample Sizes</span>
              <span className="flex-1">Longitudinal Studies</span>
              <span className="flex-1">Offline Capabilities</span>
              <span className="flex-1">Cross-regional</span>
            </div>
          </Card>
          
          <Card className="p-6">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">Identified Gap Clusters</h3>
            <div className="space-y-3">
              {[
                { title: 'Offline Machine Learning models', count: 24 },
                { title: 'Yoruba Dialect variations in NLP', count: 18 },
                { title: 'Post-harvest loss data tracking', count: 12 }
              ].map((gap, i) => (
                <div key={i} className="p-3 border border-slate-200 rounded-lg hover:border-[#00502F] cursor-pointer transition-colors" onClick={() => navigate('gap-detail')}>
                  <h4 className="text-sm font-medium text-slate-800">{gap.title}</h4>
                  <span className="text-xs text-slate-500 mt-1 block">Cited as limitation in {gap.count} theses</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen25GapExplorer;
