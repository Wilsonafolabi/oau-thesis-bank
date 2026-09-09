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

const Screen28AIAnswer = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="AI Research Assistant">
      <div className="max-w-4xl mx-auto h-[80vh] flex flex-col bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        
        {/* Chat Area (Populated) */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* User Message */}
          <div className="flex justify-end">
            <div className="bg-slate-100 text-slate-800 p-4 rounded-2xl rounded-tr-sm max-w-[80%] text-sm">
              What methodologies are common in OAU NLP research regarding the Yoruba language?
            </div>
          </div>

          {/* AI Message */}
          <div className="flex items-start space-x-3">
            <div className="w-8 h-8 rounded-full bg-[#00502F] flex-shrink-0 flex items-center justify-center mt-1">
              <Cpu className="w-4 h-4 text-white"/>
            </div>
            <div className="flex-1">
              <div className="bg-emerald-50 border border-emerald-100 text-slate-800 p-5 rounded-2xl rounded-tl-sm text-sm leading-relaxed">
                <p className="mb-4">Based on my analysis of 56 recent theses in the Computer Science department relating to Natural Language Processing (NLP) and Yoruba:</p>
                <ul className="list-disc pl-5 space-y-2 mb-4">
                  <li><strong>Transformer Models (Recent Trend):</strong> Since 2021, fine-tuning pre-trained models like mBERT and XLM-RoBERTa has become the dominant approach for tasks like sentiment analysis and Named Entity Recognition (NER) [1].</li>
                  <li><strong>Rule-Based Systems:</strong> Earlier works (2015-2019) primarily relied on grammatical rule-based approaches, especially for tone-marking and basic machine translation [2].</li>
                  <li><strong>N-gram & Hidden Markov Models (HMM):</strong> Frequently used as baseline models for part-of-speech (POS) tagging before the shift to deep learning [3].</li>
                </ul>
                <p>A recurring limitation across these methodologies is the scarcity of large, high-quality, tone-marked annotated datasets.</p>
                
                {/* Sources */}
                <div className="mt-6 pt-4 border-t border-emerald-200">
                  <span className="text-xs font-bold text-emerald-800 uppercase tracking-wider block mb-2">Sources Referenced</span>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <button className="text-left bg-white p-2 border border-emerald-200 rounded flex items-start space-x-2 hover:border-[#00502F]" onClick={() => navigate('thesis-detail')}>
                      <span className="text-xs font-bold text-emerald-600">[1]</span>
                      <span className="text-xs text-slate-600 truncate">NLP for Yoruba Text Classification (Adetunji, 2024)</span>
                    </button>
                    <button className="text-left bg-white p-2 border border-emerald-200 rounded flex items-start space-x-2 hover:border-[#00502F]" onClick={() => navigate('thesis-detail')}>
                      <span className="text-xs font-bold text-emerald-600">[2]</span>
                      <span className="text-xs text-slate-600 truncate">Rule-based Tone Marking... (Olayemi, 2018)</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-slate-200 bg-white">
          <div className="relative">
            <input type="text" placeholder="Ask a follow-up question..." className="w-full pl-4 pr-12 py-3 bg-slate-50 border border-slate-300 rounded-full focus:outline-none focus:ring-2 focus:ring-[#00502F]" />
            <button className="absolute right-2 top-1.5 p-2 bg-[#00502F] text-white rounded-full"><Send className="w-4 h-4"/></button>
          </div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen28AIAnswer;
