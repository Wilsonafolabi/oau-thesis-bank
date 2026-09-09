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

const Screen27AIAssistant = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="AI Research Assistant">
      <div className="max-w-4xl mx-auto h-[80vh] flex flex-col bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        
        {/* Chat Header */}
        <div className="bg-slate-50 p-4 border-b border-slate-200 flex items-center">
          <div className="w-10 h-10 rounded-full bg-[#00502F] flex items-center justify-center mr-3">
            <Cpu className="w-5 h-5 text-white"/>
          </div>
          <div>
            <h2 className="font-semibold text-slate-900">OAU Research Intelligence</h2>
            <p className="text-xs text-slate-500">I have read and indexed 12,400+ OAU theses.</p>
          </div>
        </div>

        {/* Chat Area (Empty State) */}
        <div className="flex-1 overflow-y-auto p-6 flex flex-col justify-center items-center text-center">
          <Cpu className="w-12 h-12 text-slate-200 mb-4" />
          <h3 className="text-lg font-medium text-slate-700 mb-6">How can I assist your research today?</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
            {[
              "What methodologies are common in OAU NLP research?",
              "Find researchers who have worked with NIMET datasets.",
              "Summarize the impact of fintech on SMEs based on recent theses.",
              "What are the major research gaps in civil engineering?"
            ].map(prompt => (
              <button key={prompt} className="text-left text-sm p-3 border border-slate-200 rounded-lg hover:border-[#00502F] hover:bg-emerald-50 transition-colors text-slate-600" onClick={() => navigate('ai-answer')}>
                "{prompt}"
              </button>
            ))}
          </div>
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-slate-200 bg-white">
          <div className="relative">
            <input 
              type="text" 
              placeholder="Ask a question about OAU research..." 
              className="w-full pl-4 pr-12 py-3 bg-slate-50 border border-slate-300 rounded-full focus:outline-none focus:ring-2 focus:ring-[#00502F] focus:border-transparent"
              onKeyDown={(e) => { if(e.key==='Enter') navigate('ai-answer') }}
            />
            <button className="absolute right-2 top-1.5 p-2 bg-[#00502F] text-white rounded-full hover:bg-[#003d24]" onClick={() => navigate('ai-answer')}>
              <Send className="w-4 h-4"/>
            </button>
          </div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen27AIAssistant;
