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

const Screen11PdfReader = () => {
  const { navigate } = useAppRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="h-screen flex flex-col bg-[#F3F4F6]">
      {/* Toolbar */}
      <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 shadow-sm z-10">
        <div className="flex items-center space-x-4">
          <button onClick={() => navigate('thesis-detail')} className="p-2 hover:bg-slate-100 rounded-md text-slate-500"><ArrowLeft className="w-5 h-5"/></button>
          <span className="font-medium text-slate-800 text-sm truncate max-w-xs">Machine Learning for Crop Yield...</span>
        </div>
        <div className="flex items-center space-x-2 bg-slate-100 rounded p-1">
          <button className="px-2 py-1 text-slate-600 hover:bg-white rounded text-sm">-</button>
          <span className="text-xs font-medium text-slate-500 px-2">100%</span>
          <button className="px-2 py-1 text-slate-600 hover:bg-white rounded text-sm">+</button>
        </div>
        <div className="flex items-center space-x-2">
          <button className="p-2 text-slate-500 hover:bg-slate-100 rounded-md" title="Download"><Download className="w-4 h-4"/></button>
          <button className={`p-2 rounded-md flex items-center ${sidebarOpen ? 'bg-emerald-50 text-emerald-700' : 'text-slate-500 hover:bg-slate-100'}`} onClick={() => setSidebarOpen(!sidebarOpen)}>
            <Cpu className="w-4 h-4 mr-1"/> <span className="text-xs font-medium">AI Assistant</span>
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Thumbnails (Simulated) */}
        <div className="w-48 bg-slate-50 border-r border-slate-200 overflow-y-auto p-4 hidden md:block">
          {[1,2,3,4].map(page => (
            <div key={page} className={`aspect-[1/1.4] bg-white border ${page===1 ? 'border-[#00502F] ring-2 ring-[#00502F] ring-opacity-20' : 'border-slate-200'} shadow-sm mb-4 flex items-center justify-center text-slate-300 text-2xl`}>
              {page}
            </div>
          ))}
        </div>

        {/* Main Document View */}
        <div className="flex-1 overflow-y-auto p-8 flex justify-center bg-slate-200">
          <div className="w-full max-w-3xl aspect-[1/1.414] bg-white shadow-xl border border-slate-300 p-12">
            <h1 className="text-center text-2xl font-bold mt-20">CHAPTER ONE</h1>
            <h2 className="text-center text-xl font-semibold mt-4">INTRODUCTION</h2>
            <p className="mt-8 text-justify text-slate-800 leading-loose">
              Agriculture remains a cornerstone of the Nigerian economy. However, predicting crop yields accurately continues to be a significant challenge due to highly variable climate conditions...
            </p>
          </div>
        </div>

        {/* AI Sidebar */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.div initial={{ width: 0, opacity: 0 }} animate={{ width: 320, opacity: 1 }} exit={{ width: 0, opacity: 0 }} className="bg-white border-l border-slate-200 flex flex-col h-full shadow-lg">
              <div className="p-4 border-b border-slate-200 bg-emerald-50">
                <h3 className="font-semibold text-emerald-900 flex items-center"><Cpu className="w-4 h-4 mr-2"/> Document Assistant</h3>
                <p className="text-xs text-emerald-700 mt-1">Ask questions about this specific thesis.</p>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                <div className="bg-slate-100 p-3 rounded-lg rounded-tl-none text-sm text-slate-700 inline-block max-w-[90%]">
                  Hi! I've analyzed this 145-page document. What would you like to know?
                </div>
                {/* Suggestions */}
                <div className="space-y-2 mt-4">
                  {['What is the methodology?', 'Summarize chapter 2', 'List the datasets used'].map(q => (
                    <button key={q} className="block w-full text-left text-xs p-2 border border-slate-200 rounded text-slate-600 hover:border-[#00502F] hover:text-[#00502F]">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
              <div className="p-4 border-t border-slate-200">
                <div className="relative">
                  <input type="text" placeholder="Ask a question..." className="w-full py-2 pl-3 pr-10 border border-slate-300 rounded-md text-sm focus:outline-none focus:border-[#00502F]" />
                  <button className="absolute right-2 top-1.5 text-slate-400 hover:text-[#00502F]"><Send className="w-4 h-4"/></button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default Screen11PdfReader;
