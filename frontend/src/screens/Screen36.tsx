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

const Screen36Conversation = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Messages">
       <div className="bg-white border border-slate-200 rounded-xl shadow-sm flex h-[75vh] overflow-hidden">
        {/* List (Hidden on mobile when in convo) */}
        <div className="hidden lg:flex w-1/3 border-r border-slate-200 flex-col">
           {MOCK_MESSAGES.map((msg, i) => (
              <div key={msg.id} className={`p-4 border-b border-slate-100 cursor-pointer ${i===0 ? 'bg-emerald-50/50 border-l-4 border-l-[#00502F]' : 'hover:bg-slate-50'}`}>
                <div className="flex justify-between items-baseline mb-1">
                  <h4 className="text-sm font-semibold text-slate-900">{msg.sender}</h4>
                </div>
                <p className="text-sm truncate text-slate-500">{msg.text}</p>
              </div>
            ))}
        </div>

        {/* Active Convo */}
        <div className="flex-1 flex flex-col w-full">
          <div className="p-4 border-b border-slate-200 flex items-center bg-white">
            <button className="lg:hidden mr-3 text-slate-500" onClick={() => navigate('messages')}><ArrowLeft className="w-5 h-5"/></button>
            <div className="w-8 h-8 rounded-full bg-slate-200 flex justify-center items-center font-bold text-slate-600 mr-3">OF</div>
            <div>
              <h3 className="font-semibold text-slate-900 text-sm">Dr. O. A. Fajemisin</h3>
              <p className="text-xs text-slate-500">Supervisor</p>
            </div>
            <div className="ml-auto">
              <button className="p-2 text-slate-400 hover:text-slate-600"><MoreVertical className="w-4 h-4"/></button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50">
            <div className="text-center text-xs text-slate-400 my-4">Today</div>
            
            <div className="flex items-start max-w-[80%]">
              <div className="w-8 h-8 rounded-full bg-slate-200 flex-shrink-0 mr-2 mt-1"></div>
              <div className="bg-white border border-slate-200 p-3 rounded-2xl rounded-tl-sm text-sm text-slate-800 shadow-sm">
                Adekunle, have you updated the methodology chapter based on our last meeting? I need to review it before the departmental defense.
                <span className="block text-[10px] text-slate-400 mt-1 text-right">10:00 AM</span>
              </div>
            </div>

            <div className="flex items-start justify-end w-full">
              <div className="bg-[#00502F] text-white p-3 rounded-2xl rounded-tr-sm text-sm shadow-sm max-w-[80%]">
                Yes sir. I just uploaded the new draft to the repository. I expanded the section on Random Forest hyperparameters as you suggested.
                <div className="mt-2 p-2 bg-[#003d24] rounded flex items-center cursor-pointer" onClick={() => navigate('thesis-detail')}>
                  <FileText className="w-4 h-4 mr-2"/> <span className="text-xs underline">View Thesis Draft</span>
                </div>
                <span className="block text-[10px] text-emerald-200 mt-1 text-right">10:15 AM</span>
              </div>
            </div>
          </div>

          <div className="p-4 bg-white border-t border-slate-200">
            <div className="flex items-center space-x-2">
              <button className="p-2 text-slate-400 hover:text-slate-600"><LinkIcon className="w-5 h-5"/></button>
              <input type="text" placeholder="Type a message..." className="flex-1 py-2 px-4 bg-slate-100 rounded-full text-sm outline-none focus:ring-1 focus:ring-[#00502F]"/>
              <button className="p-2 bg-[#00502F] text-white rounded-full hover:bg-[#003d24]"><Send className="w-4 h-4"/></button>
            </div>
          </div>
        </div>
       </div>
    </AuthenticatedLayout>
  );
};

export default Screen36Conversation;
