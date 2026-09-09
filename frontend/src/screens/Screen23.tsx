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

const Screen23IdeaSimilarity = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Similarity Analysis Results">
      <div className="max-w-5xl mx-auto space-y-8">
        <div className="bg-white p-6 rounded-xl border border-slate-200 flex flex-col md:flex-row items-center justify-between gap-6 shadow-sm">
          <div className="flex-1">
            <h3 className="text-sm uppercase tracking-wider text-slate-500 font-bold mb-2">Your Proposed Idea</h3>
            <p className="text-slate-800 font-medium italic">"Using CNNs to detect malaria parasites in blood smears via mobile attachments."</p>
          </div>
          <div className="text-center p-4 bg-amber-50 rounded-lg border border-amber-200 min-w-[200px]">
            <span className="block text-4xl font-extrabold text-amber-600">82%</span>
            <span className="text-sm font-medium text-amber-800">High Conceptual Similarity</span>
          </div>
        </div>

        <div>
          <div className="flex justify-between items-end mb-4">
            <h3 className="text-xl font-bold text-slate-900">Similar Existing Projects</h3>
            <Button variant="secondary" onClick={() => navigate('idea-extension')}>View How to Differentiate</Button>
          </div>
          
          <div className="space-y-4">
            {[1, 2].map((item, i) => (
              <Card key={i} className="p-6 relative overflow-hidden">
                <div className={`absolute top-0 left-0 w-2 h-full ${i===0 ? 'bg-amber-400' : 'bg-yellow-300'}`}></div>
                <div className="flex justify-between items-start mb-2 pl-4">
                  <h4 className="text-lg font-semibold text-slate-900 cursor-pointer hover:underline" onClick={() => navigate('thesis-detail')}>Mobile-Based Microscopic Diagnosis of Malaria using Deep Learning</h4>
                  <Badge variant="gold">{i===0 ? '82% Match' : '65% Match'}</Badge>
                </div>
                <p className="text-sm text-slate-500 pl-4 mb-4">Dept of Computer Science • 2022</p>
                
                <div className="pl-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div className="bg-slate-50 p-3 rounded">
                    <span className="block font-semibold text-slate-700 mb-1">Overlap Areas</span>
                    <span className="text-slate-600">CNN methodology, mobile microscopy focus, malaria parasite detection.</span>
                  </div>
                  <div className="bg-emerald-50 p-3 rounded">
                    <span className="block font-semibold text-[#00502F] mb-1">Their Limitations (Your Opportunity)</span>
                    <span className="text-slate-600 italic">"The model struggled with varying lighting conditions typical of low-cost mobile attachments..."</span>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen23IdeaSimilarity;
